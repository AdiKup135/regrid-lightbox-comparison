"""
ca_zoning_client.py
-------------------
Zoning district for a point, from California's own statewide zoning layer.

The state (OPR, via the National Zoning Atlas collection) publishes zoning
districts transposed onto assessor parcel geometries as hosted feature layers
on the CA Geoportal — 535 of 539 jurisdictions. One keyless point query yields
the district code and description, which is all the edge-labeling pipeline
consumes from Zoneomics' zone_details (``zone_code`` / ``zone_type``).

Vintage caveat, by design: the statewide collection is a snapshot (source
dates mostly 2022-2024; the hosted layer name pins its publication). Districts
remapped since may be stale, so the record carries ``source`` and ``date``
verbatim and fetch_parcel_context flags the payload — a first-pass district
label, not a legal determination. Per-city live layers are the upgrade path if
staleness ever bites.

All six registry counties sit in the North layer; the South layer constant is
kept for a future territory that crosses the split. Client contract mirrors
sheets/zoneomics_client.py: best-effort, never raises, None on failure.
"""
from typing import Any, Dict, Optional

import requests

_ZONING_NORTH_URL = 'https://services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/California_Statewide_Zoning_North/FeatureServer/1'
_ZONING_SOUTH_URL = 'https://services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/California_Statewide_Zoning_South/FeatureServer/1'
_TIMEOUT_SECONDS = 20


def _log_error(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request."""
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def fetch_zone_at_point(lat: float, lng: float, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
  """Zoning district containing a coordinate.

  @param lat @param lng The point, EPSG:4326 — use a point guaranteed inside
    the subject parcel (its representative point, not its centroid, which can
    fall outside an L-shaped lot).
  @param session Optional requests.Session for connection reuse.

  @return None on failure or no district, else:
    {
      'zone_code': 'R-1', 'zone_type': 'Residential Single-Family',
      'jurisdiction': 'Palo Alto',      # the layer's own attribution, a cross-check
      'source': 'City REST', 'date': '7/16/2023',
    }
  """
  http = session or requests
  params = {
    'geometry': '%s,%s' % (lng, lat),
    'geometryType': 'esriGeometryPoint',
    'inSR': 4326,
    'spatialRel': 'esriSpatialRelIntersects',
    'outFields': 'County,Jurisdiction,Code,Description,Source,Date',
    'returnGeometry': 'false',
    'f': 'json',
  }
  try:
    response = http.get('%s/query' % _ZONING_NORTH_URL, params=params, timeout=_TIMEOUT_SECONDS)
  except Exception as error:
    _log_error('ca_zoning: query threw for (%s, %s): %s' % (lat, lng, error))
    return None
  if not response.ok:
    _log_error('ca_zoning: query failed (status %s)' % response.status_code)
    return None
  try:
    payload = response.json()
  except Exception as error:
    _log_error('ca_zoning: bad JSON: %s' % error)
    return None
  if payload.get('error'):
    _log_error('ca_zoning: in-band error: %s' % payload['error'])
    return None

  features = payload.get('features') or []
  if not features:
    return None
  attributes = features[0].get('attributes') or {}
  code = (attributes.get('Code') or '').strip()
  if not code:
    return None
  return {
    'zone_code': code,
    'zone_type': (attributes.get('Description') or '').strip() or None,
    'jurisdiction': (attributes.get('Jurisdiction') or '').strip() or None,
    'source': attributes.get('Source'),
    'date': attributes.get('Date'),
  }
