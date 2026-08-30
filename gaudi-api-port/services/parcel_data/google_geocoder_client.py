"""
google_geocoder_client.py
-------------------------
Google Geocoding as the primary address oracle for the open-data provider.

Address interpretation is the one step of the free stack with no reliable free
replacement: Google resolves misspellings, unit suffixes, and vanity names to
a ROOFTOP coordinate, where the Census benchmark interpolates along TIGER
street ranges and intermittently drops whole requests. So the provider treats
geocoding exactly the way the labeling engine treats street naming: Google is
the higher-precedence oracle when a key is present, the Census path is the
keyless fallback — and in gaudi-api the call disappears entirely for most
lookups, because Project.address already persists a Google Places result
(rooftop lat/lng + the parsed ``route``).

What is deliberately NOT taken from Google: the zoning jurisdiction. Google's
``locality`` is the postal city, which lies for unincorporated pockets — an
unincorporated San Mateo County address happily says 'Redwood City'. Political
containment comes from the Census geographies-for-point lookup instead
(census_geocoder_client.geographies_for_point); the locality here is only a
flagged fallback.

Client contract mirrors sheets/zoneomics_client.py: best-effort, never raises,
returns None on any failure, short-circuits on a missing key.
"""
from typing import Any, Dict, Optional

import requests

_GEOCODE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
_TIMEOUT_SECONDS = 10


def _log_error(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request."""
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def _component(components: list, wanted_type: str) -> Optional[str]:
  for component in components or []:
    if wanted_type in (component.get('types') or []):
      return component.get('long_name') or component.get('short_name')
  return None


def fetch_geocode(address: str, api_key: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
  """Geocode a one-line address via Google.

  @param address One-line address, e.g. '1590 Madrono Ave, Palo Alto, CA'.
  @param api_key Google API key. Server-side only — never ship this to a browser.
  @param session Optional requests.Session for connection reuse.

  @return None on any failure or no result, else:
    {
      'lat': float, 'lng': float,
      'matched_address': str,           # Google's formatted_address
      'house_number': Optional[str],    # street_number component
      'street_name': Optional[str],     # the `route` component — feeds subject_street_name
      'locality': Optional[str],        # postal city; fallback jurisdiction ONLY
      'county_name': Optional[str],     # admin_area_level_2 minus ' County'
      'location_type': str,             # 'ROOFTOP' | 'RANGE_INTERPOLATED' | ...
    }
  """
  if not address or not address.strip() or not api_key:
    return None
  http = session or requests
  try:
    response = http.get(_GEOCODE_URL, params={'address': address, 'key': api_key}, timeout=_TIMEOUT_SECONDS)
  except Exception as error:
    _log_error('google_geocode: request threw for address %r: %s' % (address, error))
    return None
  if not response.ok:
    _log_error('google_geocode: failed for address %r (status %s)' % (address, response.status_code))
    return None
  try:
    payload = response.json()
  except Exception as error:
    _log_error('google_geocode: bad JSON for address %r: %s' % (address, error))
    return None
  status = payload.get('status')
  if status not in ('OK', 'ZERO_RESULTS'):
    _log_error('google_geocode: API status %s for address %r' % (status, address))
    return None
  results = payload.get('results') or []
  if not results:
    return None
  result = results[0]

  location = ((result.get('geometry') or {}).get('location')) or {}
  lat, lng = location.get('lat'), location.get('lng')
  if lat is None or lng is None:
    return None
  components = result.get('address_components') or []
  county = _component(components, 'administrative_area_level_2')
  if county and county.lower().endswith(' county'):
    county = county[:-len(' county')]

  return {
    'lat': float(lat),
    'lng': float(lng),
    'matched_address': result.get('formatted_address') or '',
    'house_number': _component(components, 'street_number'),
    'street_name': _component(components, 'route'),
    'locality': _component(components, 'locality'),
    'county_name': county,
    'location_type': ((result.get('geometry') or {}).get('location_type')) or '',
  }
