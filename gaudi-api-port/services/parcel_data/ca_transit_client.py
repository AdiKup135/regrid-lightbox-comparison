"""
ca_transit_client.py
--------------------
Is the lot within a half-mile of high-quality transit? From Caltrans' own layer.

Gov. Code § 66321(b)(4)(B) lets a detached ADU reach 18 ft (instead of 16)
when the lot is within a half-mile walking distance of a major transit stop or
a high-quality transit corridor (PRC 21064.3, 21155). Caltrans / Cal-ITP
publish "CA HQ Transit Areas" — the half-mile buffers around exactly those
stops and corridors, rebuilt monthly from every operator's GTFS and already
updated for AB 2553's 20-minute headway — as a keyless ArcGIS feature layer.
One point-in-polygon query answers the question for any California address.

Two deliberate limits, both surfaced by the caller as flags (FOR-1422):

* The buffers are straight-line, the statute says walking distance. Outside
  every buffer is a definitive no; inside is probable, not proven.
* Planned stops from MPO plans are in the layer too. The HCD Handbook defines
  a major transit stop as an EXISTING station, so rows carrying a plan name
  are dropped here.

Client contract mirrors ca_zoning_client.py: best-effort, never raises, None
on failure so the height gate can say "lookup failed" rather than guess.
"""
from typing import Any, Dict, List, Optional

import requests

_HQ_TRANSIT_AREAS_URL = 'https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHrailroad/CA_HQ_Transit_Areas/FeatureServer/0'
_TIMEOUT_SECONDS = 20
_OUT_FIELDS = 'hqta_type,hqta_details,agency_primary,agency_secondary,route_id'


def _log_error(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request."""
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def _is_planned(attributes: Dict[str, Any]) -> bool:
  # The areas layer has no plan_name column; planned stops surface through
  # hqta_details. Keep the test on the details text so a schema change that
  # adds plan_name later is also caught.
  details = str(attributes.get('hqta_details') or '').lower()
  return 'planned' in details or bool(str(attributes.get('plan_name') or '').strip())


def fetch_transit_at_point(lat: float, lng: float, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
  """High-quality transit areas containing a coordinate.

  @param lat @param lng The point, EPSG:4326 — the subject parcel's point.
  @param session Optional requests.Session for connection reuse.

  @return None on failure, else:
    {
      'near_transit': True,                     # inside ≥ 1 existing-stop/corridor buffer
      'hqta_types': ['major_stop_bus', 'hq_corridor_bus'],
      'agencies': ['Santa Clara Valley Transportation Authority'],
      'routes': ['22', 'Rapid 522'],
      'area_count': 2, 'planned_dropped': 0,
      'source': 'Caltrans / Cal-ITP CA HQ Transit Areas',
      'distance_basis': 'half_mile_straight_line_buffer',
    }
  """
  http = session or requests
  params = {
    'geometry': '%s,%s' % (lng, lat),
    'geometryType': 'esriGeometryPoint',
    'inSR': 4326,
    'spatialRel': 'esriSpatialRelIntersects',
    'outFields': _OUT_FIELDS,
    'returnGeometry': 'false',
    'f': 'json',
  }
  try:
    response = http.get('%s/query' % _HQ_TRANSIT_AREAS_URL, params=params, timeout=_TIMEOUT_SECONDS)
  except Exception as error:
    _log_error('ca_transit: query threw for (%s, %s): %s' % (lat, lng, error))
    return None
  if not response.ok:
    _log_error('ca_transit: query failed (status %s)' % response.status_code)
    return None
  try:
    payload = response.json()
  except Exception as error:
    _log_error('ca_transit: bad JSON: %s' % error)
    return None
  if payload.get('error'):
    _log_error('ca_transit: in-band error: %s' % payload['error'])
    return None

  features: List[Dict[str, Any]] = payload.get('features') or []
  existing = [f.get('attributes') or {} for f in features if not _is_planned(f.get('attributes') or {})]

  def distinct(key: str) -> List[str]:
    seen: List[str] = []
    for a in existing:
      value = str(a.get(key) or '').strip()
      if value and value not in seen:
        seen.append(value)
    return sorted(seen)

  agencies = sorted(set(distinct('agency_primary') + distinct('agency_secondary')))
  return {
    'near_transit': bool(existing),
    'hqta_types': distinct('hqta_type'),
    'agencies': agencies,
    'routes': distinct('route_id'),
    'area_count': len(existing),
    'planned_dropped': len(features) - len(existing),
    'source': 'Caltrans / Cal-ITP CA HQ Transit Areas',
    'distance_basis': 'half_mile_straight_line_buffer',
  }
