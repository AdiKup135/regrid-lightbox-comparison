"""
arcgis_parcel_client.py
-----------------------
County-agnostic ArcGIS REST client for assessor parcel fabrics.

Every county in county_registry serves its parcels from an ArcGIS
FeatureServer or MapServer layer, and both speak the same ``/query`` dialect —
so one client handles all six, parameterized entirely by the registry config.
Two query shapes cover the provider's needs:

* point-intersects — which parcel is at this coordinate (subject lookup);
* envelope-intersects — every parcel touching a bbox (neighbour discovery).
  This is the structural win over the Zoneomics pattern: one request returns
  every neighbour WITH geometry, where Zoneomics needed a discovery query plus
  one point query per neighbour (the "2+N" pattern its API makes irreducible).

Results are normalized to the provider-agnostic parcel record the labeling
engine already consumes: ``{apn, address, lat, lng, boundary}`` with boundary
as WKT in EPSG:4326 lng/lat order and lat/lng the polygon centroid — the same
contract Zoneomics parcels arrive in, so everything downstream is unchanged.

Geometry-only fabrics (situs_mode 'join') get their situs addresses attached
from the county's companion address point layer via one batched ``APN IN``
attribute query — see attach_joined_situs.

Transport contract mirrors sheets/zoneomics_client.py: best-effort, never
raises, returns None on failure, logs through the request-bound fx_logger.
ArcGIS reports errors in-band with HTTP 200, so ``error`` payloads are checked
explicitly. f=geojson is asked for first; older MapServers that cannot produce
it fall back to Esri JSON, whose rings are converted here (clockwise ring =
shell, counter-clockwise = hole, per the Esri spec).
"""
from typing import Any, Dict, List, Optional

import requests
from shapely.geometry import MultiPolygon, Polygon, shape

from .county_registry import CountyConfig

_TIMEOUT_SECONDS = 20

# Neighbour envelopes on small-town blocks return well under this; it exists so
# a degenerate envelope (bad subject geometry) cannot pull a whole county.
_MAX_ENVELOPE_RECORDS = 200


def _log_error(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request."""
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def _query(layer_url: str, params: Dict[str, Any], session: Optional[requests.Session]) -> Optional[Dict[str, Any]]:
  """One /query call. Returns the parsed payload, or None on any failure."""
  http = session or requests
  try:
    response = http.get('%s/query' % layer_url, params=params, timeout=_TIMEOUT_SECONDS)
  except Exception as error:
    _log_error('arcgis: query to %s threw: %s' % (layer_url, error))
    return None
  if not response.ok:
    _log_error('arcgis: query to %s failed (status %s)' % (layer_url, response.status_code))
    return None
  try:
    payload = response.json()
  except Exception as error:
    _log_error('arcgis: bad JSON from %s: %s' % (layer_url, error))
    return None
  if isinstance(payload, dict) and payload.get('error'):
    _log_error('arcgis: in-band error from %s: %s' % (layer_url, payload['error']))
    return None
  return payload


def _esri_rings_to_geometry(rings: List[List[List[float]]]) -> Optional[MultiPolygon]:
  """Esri JSON rings -> shapely MultiPolygon (clockwise shell, ccw hole)."""
  shells: List[Polygon] = []
  holes: List[Polygon] = []
  for ring in rings or []:
    if len(ring) < 4:
      continue
    try:
      ring_polygon = Polygon(ring)
    except Exception:
      continue
    if ring_polygon.is_empty:
      continue
    # Esri: clockwise = exterior. Shapely's signed area is positive for ccw.
    (holes if ring_polygon.exterior.is_ccw else shells).append(ring_polygon)
  if not shells and holes:
    shells, holes = holes, []  # tolerate fabrics with inverted orientation
  if not shells:
    return None
  polygons = []
  for shell in shells:
    interior = [hole.exterior.coords for hole in holes if shell.contains(hole.representative_point())]
    polygons.append(Polygon(shell.exterior.coords, interior))
  return MultiPolygon(polygons)


def _feature_geometry(feature: Dict[str, Any], from_geojson: bool) -> Optional[MultiPolygon]:
  """Shapely geometry of one returned feature, in either response dialect."""
  try:
    if from_geojson:
      geometry = shape(feature.get('geometry') or {})
      if geometry.is_empty:
        return None
      if isinstance(geometry, Polygon):
        geometry = MultiPolygon([geometry])
      return geometry if isinstance(geometry, MultiPolygon) else None
    return _esri_rings_to_geometry((feature.get('geometry') or {}).get('rings') or [])
  except Exception:
    return None


def compose_situs(attributes: Dict[str, Any], components: List[str]) -> str:
  """Join the non-empty situs columns with spaces: ['1590','','MADRONO','AV'] -> '1590 MADRONO AV'."""
  parts = []
  for component in components:
    value = attributes.get(component)
    text = str(value).strip() if value is not None else ''
    if text:
      parts.append(text)
  return ' '.join(parts)


def _normalize_features(payload: Dict[str, Any], county: CountyConfig, from_geojson: bool) -> List[Dict[str, Any]]:
  """ArcGIS features -> provider-agnostic parcel records (situs left to the caller for join counties)."""
  records: List[Dict[str, Any]] = []
  components = list(county.get('situs_components') or [])
  for feature in payload.get('features') or []:
    attributes = (feature.get('properties') if from_geojson else feature.get('attributes')) or {}
    geometry = _feature_geometry(feature, from_geojson)
    if geometry is None:
      continue
    apn = str(attributes.get(str(county['apn_field'])) or '').strip()
    if not apn:
      continue
    centroid = geometry.centroid
    records.append({
      'apn': apn,
      'address': compose_situs(attributes, components) if county.get('situs_mode') == 'fields' else '',
      'lat': centroid.y,
      'lng': centroid.x,
      'boundary': geometry.wkt,
      'situs_city': str(attributes.get(str(county.get('city_field'))) or '').strip() or None,
    })
  return records


def _out_fields(county: CountyConfig) -> str:
  """Only the columns the normalizer reads — outFields=* drags every assessor
  column (Sonoma: ~100) across the wire for every parcel in the envelope."""
  fields = [str(county['apn_field'])]
  if county.get('situs_mode') == 'fields':
    fields += [str(c) for c in county.get('situs_components') or []]
  if county.get('city_field'):
    fields.append(str(county['city_field']))
  return ','.join(dict.fromkeys(f for f in fields if f))


def _spatial_query(county: CountyConfig, geometry: str, geometry_type: str,
                   session: Optional[requests.Session]) -> Optional[List[Dict[str, Any]]]:
  """Run one spatial query, preferring GeoJSON and falling back to Esri JSON."""
  layer_url = str(county['parcel_layer_url'])
  base = {
    'geometry': geometry,
    'geometryType': geometry_type,
    'inSR': 4326,
    'spatialRel': 'esriSpatialRelIntersects',
    'outFields': _out_fields(county),
    'outSR': 4326,
    'returnGeometry': 'true',
    # ~0.1 m; parcel fabrics ship far more digits than the engine can use.
    'geometryPrecision': 6,
    'resultRecordCount': _MAX_ENVELOPE_RECORDS,
  }
  payload = _query(layer_url, dict(base, f='geojson'), session)
  if payload is not None and 'features' in payload:
    return _normalize_features(payload, county, from_geojson=True)
  payload = _query(layer_url, dict(base, f='json'), session)
  if payload is None:
    return None
  return _normalize_features(payload, county, from_geojson=False)


def fetch_parcels_at_point(county: CountyConfig, lat: float, lng: float,
                           session: Optional[requests.Session] = None) -> Optional[List[Dict[str, Any]]]:
  """Parcels whose geometry contains a coordinate (several for stacked condo fabrics).

  @param county A county_registry config.
  @param lat @param lng The point, EPSG:4326.
  @return Normalized parcel records, [] for a point in the right-of-way, None on transport failure.
  """
  return _spatial_query(county, '%s,%s' % (lng, lat), 'esriGeometryPoint', session)


def fetch_parcels_in_envelope(county: CountyConfig, xmin: float, ymin: float, xmax: float, ymax: float,
                              session: Optional[requests.Session] = None) -> Optional[List[Dict[str, Any]]]:
  """Every parcel intersecting a lng/lat envelope, geometry included — the one-call neighbour discovery.

  @param county A county_registry config.
  @param xmin @param ymin @param xmax @param ymax Envelope corners, EPSG:4326 lng/lat.
  @return Normalized parcel records, or None on transport failure.
  """
  envelope = '%s,%s,%s,%s' % (xmin, ymin, xmax, ymax)
  return _spatial_query(county, envelope, 'esriGeometryEnvelope', session)


def _fetch_situs_rows_arcgis(join: Dict[str, Any], apns: List[str],
                             session: Optional[requests.Session]) -> Optional[List[Dict[str, Any]]]:
  """Situs rows from an ArcGIS address point layer, one batched APN IN query."""
  wanted = [str(join['apn_field'])] + [str(c) for c in join.get('components') or []]
  if join.get('city_field'):
    wanted.append(str(join['city_field']))
  params = {
    'where': "%s IN (%s)" % (join['apn_field'], ','.join("'%s'" % apn for apn in apns)),
    'outFields': ','.join(dict.fromkeys(wanted)),
    'returnGeometry': 'false',
    'f': 'json',
  }
  payload = _query(str(join['layer_url']), params, session)
  if payload is None:
    return None
  return [feature.get('attributes') or {} for feature in payload.get('features') or []]


def _fetch_situs_rows_socrata(join: Dict[str, Any], apns: List[str],
                              session: Optional[requests.Session]) -> Optional[List[Dict[str, Any]]]:
  """Situs rows from a Socrata (SODA) resource, one batched `apn in(...)` query.

  Some counties publish their authoritative situs table on a Socrata portal
  rather than ArcGIS (San Mateo: data.smcgov.org). SODA speaks SoQL; the rows
  come back as plain JSON dicts keyed by fieldName, so downstream composition
  is identical to the ArcGIS shape.
  """
  http = session or requests
  soql = "%s in(%s)" % (join['apn_field'], ','.join("'%s'" % apn for apn in apns))
  try:
    response = http.get(str(join['resource_url']), params={'$where': soql, '$limit': len(apns) * 4}, timeout=_TIMEOUT_SECONDS)
  except Exception as error:
    _log_error('socrata: situs query to %s threw: %s' % (join['resource_url'], error))
    return None
  if not response.ok:
    _log_error('socrata: situs query to %s failed (status %s)' % (join['resource_url'], response.status_code))
    return None
  try:
    rows = response.json()
  except Exception as error:
    _log_error('socrata: bad JSON from %s: %s' % (join['resource_url'], error))
    return None
  return rows if isinstance(rows, list) else None


def attach_joined_situs(county: CountyConfig, parcels: List[Dict[str, Any]],
                        session: Optional[requests.Session] = None) -> bool:
  """Fill in ``address`` on geometry-only fabrics from the county's situs source.

  One batched ``APN IN (...)`` query for all parcels, against an ArcGIS address
  point layer or a Socrata resource depending on the registry config (join
  ``kind``). Where a parcel has several address rows (units), the first row
  wins — the situs street is what downstream street naming needs, and units
  share it.

  @param county A county_registry config with situs_mode 'join'.
  @param parcels Normalized parcel records, mutated in place.
  @return True if the join query succeeded (even with partial matches), False on failure.
  """
  join = county.get('situs_join')
  if not isinstance(join, dict) or not parcels:
    return True
  apns = sorted({str(p['apn']).replace("'", "''") for p in parcels})
  if join.get('kind') == 'socrata':
    rows = _fetch_situs_rows_socrata(join, apns, session)
  else:
    rows = _fetch_situs_rows_arcgis(join, apns, session)
  if rows is None:
    return False
  by_apn: Dict[str, Dict[str, Any]] = {}
  for attributes in rows:
    apn = str(attributes.get(str(join['apn_field'])) or '').strip()
    if apn and apn not in by_apn:
      by_apn[apn] = attributes
  components = list(join.get('components') or [])
  city_field = join.get('city_field')
  for parcel in parcels:
    attributes = by_apn.get(str(parcel['apn']))
    if attributes is None:
      continue
    parcel['address'] = compose_situs(attributes, components)
    if city_field and not parcel.get('situs_city'):
      parcel['situs_city'] = str(attributes.get(str(city_field)) or '').strip() or None
  return True
