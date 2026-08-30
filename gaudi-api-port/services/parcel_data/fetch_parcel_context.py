"""
fetch_parcel_context.py
-----------------------
The free provider's use case: one-line address in, the /edges wire shape out.

This is the open-data replacement for the Zoneomics fetch orchestration —
same output contract ({geocode, subject, neighbors, meta, zone, callCount,
discovery, flags} with parcels as {apn, address, lat, lng, boundary}), so the
labeling engine, the debug UI, and the label route consume it unchanged.

Source stack per lookup (4-6 HTTP calls, parallelized into ~3 round-trip
stages):

  1. address -> coordinate — Google Geocoding (rooftop; also yields the
     `route` that feeds subject_street_name), or a caller-supplied lat/lng
     (gaudi-api: Project.address already persists a Google Places geocode —
     zero geocoding calls). There is deliberately NO free-geocoder fallback
     and no situs-verification heuristics: the Census address matcher proved
     interpolated, flaky, and able to "match" onto the wrong street (the
     2026-08-30 Orinda regression), and the string-matching machinery that
     tried to compensate was removed with it. The parcel under a rooftop
     point IS the parcel; a point that misses fails loudly as no_parcel.
  2. coordinate -> jurisdiction + county — Census geographies_for_point, pure
     TIGER polygon containment, authoritative regardless of the geocode
     source (Google's locality is postal and lies for unincorporated
     pockets; it is only a flagged last resort). Runs in parallel with the
     subject-parcel point query.
  3. county parcel layer — subject at point, neighbours in ONE envelope query
     (arcgis_parcel_client + county_registry); geometry-only fabrics get
     situs attached by APN join. Runs in parallel with the zoning query.
  4. CA statewide zoning — district at the subject's representative point
     (ca_zoning_client).

Every degradation is a flag, never a silent guess — in particular a failed
neighbour query yields ``neighbor_fetch_failed`` rather than an empty fabric
that would mislabel the lot as an unnamed through lot (the Zoneomics path's
known 429 failure mode).

Errors the caller must branch on come back as {'error', 'error_kind'} —
error_kind in {'bad_request', 'no_match', 'unsupported_county', 'no_parcel',
'upstream'} — so the HTTP layer can map them without string-matching messages.

Pass a shared requests.Session: connection reuse across the stack's hosts is
worth several hundred ms per lookup (each cold call pays a fresh TLS
handshake).
"""
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
from shapely import wkt as shapely_wkt

from .arcgis_parcel_client import attach_joined_situs, fetch_parcels_at_point, fetch_parcels_in_envelope
from .ca_zoning_client import fetch_zone_at_point
from .census_geocoder_client import geographies_for_point
from .county_registry import CountyConfig, county_for_fips, county_for_name, supported_counties
from .google_geocoder_client import fetch_geocode

DEFAULT_MAX_NEIGHBORS = 12
MAX_NEIGHBORS_CAP = 20
DEFAULT_MARGIN_M = 15.0

_M_PER_DEG_LAT = 111_320.0


def _error(kind: str, message: str) -> Dict[str, Any]:
  return {'error': message, 'error_kind': kind}


def _deg_lng(meters: float, lat: float) -> float:
  return meters / (_M_PER_DEG_LAT * max(0.1, math.cos(math.radians(lat))))


def _deg_lat(meters: float) -> float:
  return meters / _M_PER_DEG_LAT


def _distance_squared_deg(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
  scale = math.cos(math.radians((a_lat + b_lat) / 2))
  return ((a_lng - b_lng) * scale) ** 2 + (a_lat - b_lat) ** 2


def _fetch_neighbors(county: CountyConfig, subject: Dict[str, Any], subject_bounds, margin_m: float,
                     max_neighbors: int, flags: List[str], calls: List[int],
                     session: Optional[requests.Session]) -> List[Dict[str, Any]]:
  """One envelope query around the subject, deduped, distance-sorted, capped, situs-joined."""
  xmin, ymin, xmax, ymax = subject_bounds
  half_lng, half_lat = _deg_lng(margin_m, subject['lat']), _deg_lat(margin_m)
  calls[0] += 1
  fabric = fetch_parcels_in_envelope(county, xmin - half_lng, ymin - half_lat, xmax + half_lng, ymax + half_lat, session=session)
  if fabric is None:
    flags.append('neighbor_fetch_failed')
    return []
  neighbors: List[Dict[str, Any]] = []
  seen = {subject['apn']}
  for parcel in fabric:
    if parcel['apn'] in seen:
      continue
    seen.add(parcel['apn'])
    neighbors.append(parcel)
  neighbors.sort(key=lambda p: _distance_squared_deg(subject['lat'], subject['lng'], p['lat'], p['lng']))
  if len(neighbors) > max_neighbors:
    neighbors = neighbors[:max_neighbors]
    flags.append('neighbors_truncated')
  if county.get('situs_mode') == 'join' and neighbors:
    calls[0] += 1
    if not attach_joined_situs(county, neighbors, session=session):
      flags.append('neighbor_situs_join_failed')
  return neighbors


def fetch_parcel_context(address: str,
                         max_neighbors: int = DEFAULT_MAX_NEIGHBORS,
                         margin_m: float = DEFAULT_MARGIN_M,
                         session: Optional[requests.Session] = None,
                         google_api_key: Optional[str] = None,
                         lat: Optional[float] = None,
                         lng: Optional[float] = None) -> Dict[str, Any]:
  """Assemble the /edges payload for an address from open-data sources.

  @param address One-line address, e.g. '1590 Madrono Ave, Palo Alto, CA'.
  @param max_neighbors Neighbour cap after distance sort (hard cap 20).
  @param margin_m Envelope margin beyond the subject's bounds for neighbour discovery.
  @param session Shared requests.Session — pass one; connection reuse matters.
  @param google_api_key Enables Google geocoding. Required unless lat/lng are given.
  @param lat @param lng A coordinate the caller already trusts (e.g. gaudi's
    persisted Project.address geocode) — skips geocoding entirely.

  @return The wire-shape dict, or {'error', 'error_kind'} — see module docstring.
  """
  if not address or not address.strip():
    return _error('bad_request', 'address is required')
  max_neighbors = max(0, min(int(max_neighbors), MAX_NEIGHBORS_CAP))
  calls = [0]
  flags: List[str] = []

  # Stage 1: the coordinate. Caller-supplied, else Google — nothing else.
  street_name: Optional[str] = None
  google: Optional[Dict[str, Any]] = None
  if lat is not None and lng is not None:
    lat, lng = float(lat), float(lng)
    geocode_source = 'caller'
  elif google_api_key:
    calls[0] += 1
    google = fetch_geocode(address, google_api_key, session=session)
    if google is None:
      return _error('no_match', 'Google could not geocode %r' % address)
    lat, lng, street_name = google['lat'], google['lng'], google.get('street_name')
    geocode_source = 'google'
    if google.get('location_type') != 'ROOFTOP':
      flags.append('geocode_not_rooftop')
  else:
    return _error('bad_request', 'no geocoder available: pass lat/lng or set GOOGLE_API_KEY '
                                 '(the free-geocoder fallback was removed as unreliable)')

  # Stages 2-3: the county adapter is only known once containment returns, so
  # the two county-independent calls (Census containment — the slowest single
  # call — and statewide zoning) start together; the parcel point query fires
  # the moment containment lands, and neighbour discovery overlaps the rest.
  with ThreadPoolExecutor(max_workers=2) as pool:
    containment_future = pool.submit(geographies_for_point, lat, lng, session)
    zone_future = pool.submit(fetch_zone_at_point, lat, lng, session)
    containment = containment_future.result()
    calls[0] += 1

    if containment is None:
      # Census containment down: fall back to Google's county/locality, flagged —
      # Google's locality is postal and can misname unincorporated pockets.
      flags.append('jurisdiction_lookup_failed')
      containment = {}
      if google is not None and (google.get('county_name') or google.get('locality')):
        flags.append('jurisdiction_from_google_locality')
        containment = {'county_name': google.get('county_name'), 'place_name': google.get('locality')}
    county = county_for_fips(containment.get('county_fips')) or county_for_name(containment.get('county_name'))
    if county is None:
      zone_future.result()
      return _error('unsupported_county',
                    'no parcel source for county %r; supported: %s'
                    % (containment.get('county_name'), ', '.join(supported_counties())))
    vintage_flag = county.get('vintage_flag')
    if vintage_flag:
      flags.append(str(vintage_flag))

    calls[0] += 1
    candidates = fetch_parcels_at_point(county, lat, lng, session=session)
    if candidates is None:
      zone_future.result()
      return _error('upstream', 'county parcel layer query failed')
    if not candidates:
      zone_future.result()
      return _error('no_parcel', 'no parcel contains the geocoded point for %r — the geocode may be '
                                 'non-rooftop or the point may fall in the right-of-way' % address)
    subject = candidates[0]
    if len(candidates) > 1:
      flags.append('multiple_parcels_at_point')

    try:
      subject_shape = shapely_wkt.loads(subject['boundary'])
    except Exception:
      zone_future.result()
      return _error('upstream', 'county fabric returned an unparseable subject boundary')

    # Stage 3, in parallel with the still-running zoning query: neighbours
    # (+ situs join) and the subject's own situs join where needed.
    neighbors_future = pool.submit(_fetch_neighbors, county, subject, subject_shape.bounds,
                                   margin_m, max_neighbors, flags, calls, session)
    if county.get('situs_mode') == 'join':
      calls[0] += 1
      attach_joined_situs(county, [subject], session=session)
    neighbors = neighbors_future.result()
    calls[0] += 1  # the zoning query
    zone_record = zone_future.result()

  zone: Optional[Dict[str, Any]] = None
  if zone_record is None:
    flags.append('zone_lookup_failed')
  else:
    zone = {'zone_code': zone_record['zone_code'], 'zone_type': zone_record.get('zone_type')}

  place_name = containment.get('place_name')
  jurisdiction = place_name or (
    '%s County (unincorporated)' % containment.get('county_name') if containment.get('county_name') else None)
  if zone_record and zone_record.get('jurisdiction') and place_name and zone_record['jurisdiction'] != place_name:
    flags.append('zone_jurisdiction_mismatch')

  return {
    'geocode': {'lat': lat, 'lng': lng},
    'subject': subject,
    'neighbors': neighbors,
    # Google's parsed `route` — outranks situs parsing inside the engine
    # (EdgeLabelingInput.subject_street_name).
    'subject_street_name': street_name,
    'meta': {
      'city_name': jurisdiction,
      'place_geoid': containment.get('place_geoid'),
      'county_name': containment.get('county_name'),
      'county_fips': containment.get('county_fips'),
      'source': 'opendata',
      'geocode_source': geocode_source,
      'parcel_source': county['parcel_layer_url'],
      'zoning_source': (zone_record or {}).get('source'),
      'zoning_vintage': (zone_record or {}).get('date'),
      'last_updated': (zone_record or {}).get('date'),
    },
    'zone': zone,
    'callCount': calls[0],
    'discovery': 'arcgis-envelope',
    'flags': flags,
  }
