"""
parcel_edges.py
---------------
HTTP surface of the free ("opendata") parcel provider + the edge labeler.

Two routes, mirroring the wire contract of the POC's Express zoneomics-backend
so the debug UI can toggle providers without changing shape:

  GET  /edges?address=...      — fetch_parcel_context: the open-data fetch
  POST /edges/label            — run the labeling engine on an /edges payload
                                 posted back verbatim (any provider's)

This is the Flask route assembly that cli.py's docstring promised gaudi-api —
written and exercised here first. Differences from a gaudi-api drop-in, all
deliberate POC scope: no @login_required (the POC app has no auth module; add
the decorator on integration), and GOOGLE_API_KEY is read from the environment
inline (gaudi-api centralizes env reads as config.py constants — move it there).
Front-rule resolution accepts both provider vocabularies: Zoneomics city_id and
the Census jurisdiction name (see services/parcel_data/front_rules.py).
"""
import os
from typing import Any, Dict

import requests
from flask import Blueprint, g, jsonify, request

from services.compute.parcel_edges.edge_labeling import (
  EdgeLabelingInput,
  FrontRuleOverride,
  ZoneomicsParcel,
  label_edges,
)
from services.parcel_data.fetch_parcel_context import DEFAULT_MAX_NEIGHBORS, fetch_parcel_context
from services.parcel_data.front_rules import front_rule_for

parcel_edges_bp = Blueprint('parcel_edges', __name__)

# One shared session for the whole provider stack: every cold call otherwise
# pays a fresh TLS handshake per upstream host, which dominated lookup latency.
_http = requests.Session()

_STATUS_BY_ERROR_KIND = {
  'bad_request': 400,
  'no_match': 404,
  'no_parcel': 404,
  'unsupported_county': 422,
  'upstream': 502,
}


def _parcel(record: Dict[str, Any]) -> ZoneomicsParcel:
  return ZoneomicsParcel(
    apn=str(record.get('apn', '')),
    address=record.get('address') or '',
    lat=float(record['lat']),
    lng=float(record['lng']),
    boundary=record['boundary'],
  )


@parcel_edges_bp.route('/edges', methods=['GET'])
def get_edges():
  """The /edges wire payload for an address, from free open-data sources."""
  try:
    address = (request.args.get('address') or '').strip()
    assert address, 'address query parameter is required'
    max_neighbors = int(request.args.get('maxNeighbors', DEFAULT_MAX_NEIGHBORS))
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    context = fetch_parcel_context(address, max_neighbors=max_neighbors,
                                   google_api_key=(os.environ.get('GOOGLE_API_KEY') or '').strip() or None,
                                   lat=lat, lng=lng, session=_http)
    if context.get('error'):
      return jsonify({'error': context['error']}), _STATUS_BY_ERROR_KIND.get(str(context.get('error_kind')), 500)
    return jsonify(context), 200
  except Exception as e:
    g.fx_logger.log('parcel_edges: /edges failed: %s' % e, channel_name='error')
    return jsonify({'error': str(e)}), 400 if isinstance(e, AssertionError) else 500


@parcel_edges_bp.route('/edges/label', methods=['POST'])
def label_edges_route():
  """Label a posted /edges payload — same in-process assembly cli.py documents."""
  try:
    body = request.get_json(silent=True) or {}
    subject = body.get('subject') or {}
    assert subject.get('boundary'), 'subject parcel with boundary required (pass the /edges response)'
    meta = body.get('meta') or {}

    if body.get('front_rule'):
      front: Dict[str, Any] = {'rule': body['front_rule'], 'overrides': body.get('front_rule_overrides')}
    else:
      front = front_rule_for(city_id=meta.get('city_id'),
                             jurisdiction_name=meta.get('city_name'),
                             county_name=meta.get('county_name')) or {}

    street_namer = None
    google_api_key = (os.environ.get('GOOGLE_API_KEY') or '').strip() or None
    if google_api_key:
      from services.compute.parcel_edges.street_naming import make_google_roads_namer
      street_namer = make_google_roads_namer(google_api_key)

    overrides = [FrontRuleOverride.from_db(o) for o in front.get('overrides') or []]
    result = label_edges(EdgeLabelingInput(
      subject=_parcel(subject),
      neighbors=[_parcel(n) for n in body.get('neighbors') or []],
      front_rule=front.get('rule'),
      front_rule_overrides=overrides or None,
      zone=body.get('zone'),
      user_front_override_edge_index=body.get('user_front_override_edge_index'),
      subject_street_name=body.get('subject_street_name'),
      street_namer=street_namer,
    ))
    return jsonify({
      'result': result.to_dict(),
      'engine': 'python',
      'front_rule_used': front.get('rule') or 'address_street (engine default)',
      'roads_namer': bool(google_api_key),
    }), 200
  except Exception as e:
    g.fx_logger.log('parcel_edges: /edges/label failed: %s' % e, channel_name='error')
    return jsonify({'error': str(e)}), 400 if isinstance(e, AssertionError) else 500
