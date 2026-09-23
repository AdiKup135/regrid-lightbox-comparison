"""
adu_setbacks.py
---------------
HTTP surface of the ADU setback engine, Phase A (the state track).

  POST /adu/evaluate — a posted /edges payload (any provider's) plus the unit
                       facts; labels the lot in-process (the same assembly as
                       /edges/label, via routes.parcel_edges.label_from_body),
                       decides the track, and on the state track returns each
                       edge's setback and the buildable envelope.

Body, on top of the /edges response fields:
  unit_size             sq ft of interior livable space — required, > 0
  unit_height_in_feet   required, > 0
  sb9_split             optional bool (default false)  — FOR-1420
  existing_detached_adu optional bool (default false)  — FOR-1421
  transit               optional; the /edges payload's own ``transit`` block.
                        When absent (Zoneomics payloads, fixtures, older
                        captures) the route runs the Caltrans lookup itself at
                        the subject point, so any provider's payload evaluates.

Kept separate from /edges/label on purpose: labeling edges is one step, this
is the evaluation pipeline that composes steps and will grow Phase B/C.
Same POC caveats as parcel_edges.py: no @login_required here.
"""
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, g, jsonify, request

import requests

from routes.parcel_edges import label_from_body
from services.compute.adu_setbacks import UnitFacts, evaluate_adu
from services.parcel_data.ca_transit_client import fetch_transit_at_point

adu_setbacks_bp = Blueprint('adu_setbacks', __name__)

# Shared session for the transit fallback lookup (connection reuse, see parcel_edges.py).
_http = requests.Session()


def _positive_number(body: Dict[str, Any], key: str) -> float:
  value = body.get(key)
  assert value is not None and value != '', '%s is required' % key
  try:
    number = float(value)
  except (TypeError, ValueError):
    raise AssertionError('%s must be a number' % key)
  assert number > 0, '%s must be positive' % key
  return number


def _resolve_transit(body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
  """The transit block to evaluate against, and where it came from.

  @return (transit record or None, 'payload' | 'lookup' | 'lookup_failed').
  """
  transit = body.get('transit')
  if isinstance(transit, dict) and 'near_transit' in transit:
    return transit, 'payload'
  subject = body.get('subject') or {}
  try:
    lat, lng = float(subject['lat']), float(subject['lng'])
  except (KeyError, TypeError, ValueError):
    return None, 'lookup_failed'
  record = fetch_transit_at_point(lat, lng, session=_http)
  return record, 'lookup' if record is not None else 'lookup_failed'


@adu_setbacks_bp.route('/adu/evaluate', methods=['POST'])
def evaluate_route():
  """Phase A: track + state-track setbacks + envelope for a posted /edges payload."""
  try:
    body = request.get_json(silent=True) or {}
    unit_size = _positive_number(body, 'unit_size')
    unit_height = _positive_number(body, 'unit_height_in_feet')
    transit, transit_source = _resolve_transit(body)
    near_transit = None if transit is None or transit.get('near_transit') is None else bool(transit['near_transit'])
    unit = UnitFacts(
      unit_size=unit_size,
      unit_height_in_feet=unit_height,
      near_transit=near_transit,
      sb9_split=bool(body.get('sb9_split', False)),
      existing_detached_adu=bool(body.get('existing_detached_adu', False)),
    )
    labeling, front, roads_namer = label_from_body(body)
    subject = body['subject']
    evaluation = evaluate_adu(unit, [e.to_dict() for e in labeling.edges], subject['boundary'],
                              float(subject['lng']), float(subject['lat']))
    payload = evaluation.to_dict()
    payload['transit'] = transit
    payload['transit_source'] = transit_source
    payload['labeling'] = {
      'flags': list(labeling.flags),
      'stats': labeling.stats.to_dict(),
      'front_rule_used': front.get('rule') or 'address_street (engine default)',
      'roads_namer': roads_namer,
      'engine': 'python',
    }
    return jsonify(payload), 200
  except Exception as e:
    g.fx_logger.log('adu_setbacks: /adu/evaluate failed: %s' % e, channel_name='error')
    return jsonify({'error': str(e)}), 400 if isinstance(e, AssertionError) else 500
