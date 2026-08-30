"""
census_geocoder_client.py
-------------------------
US Census geocoder as the jurisdiction oracle: which incorporated place (if
any) and which county contain a coordinate.

Only the ``coordinates -> geographies`` endpoint is used — pure point-in-
polygon containment against TIGER polygons, no address interpretation at all.
This is the AUTHORITATIVE source for the zoning jurisdiction and the county
FIPS that selects the parcel-fabric adapter, whatever produced the coordinate:
it beats Google's ``locality``, which reports the postal city and lies for
unincorporated pockets. No Places row in the answer IS the unincorporated-
county case (real jurisdictions in our territory), not an error.

The service's ADDRESS-matching endpoint was deliberately removed (2026-08-30):
it interpolates along TIGER street ranges rather than rooftops, fails
intermittently under load, and fuzzy-"matches" addresses on streets missing
from its benchmark onto nearby different streets — Google handles address
interpretation instead (google_geocoder_client), with no free fallback.

Client contract mirrors sheets/zoneomics_client.py: best-effort, never raises,
returns None on any failure, logs through the request-bound fx_logger when one
exists. Containment requests are retried once — the endpoint shares the
geocoder's intermittent drops.
"""
import time
from typing import Any, Dict, Optional

import requests

_COORDINATES_URL = 'https://geocoding.geo.census.gov/geocoder/geographies/coordinates'
_BENCHMARK = 'Public_AR_Current'
_VINTAGE = 'Current_Current'
_LAYERS = 'Incorporated Places,Counties'
_TIMEOUT_SECONDS = 15

# The public geocoder intermittently drops a request that succeeds seconds
# later (observed live 2026-08-30). One paced retry absorbs that.
_ATTEMPTS = 2
_RETRY_PAUSE_SECONDS = 1.5


def _log_error(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request."""
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def _extract_geographies(geographies: Dict[str, Any]) -> Dict[str, Optional[str]]:
  places = geographies.get('Incorporated Places') or []
  counties = geographies.get('Counties') or []
  place = places[0] if places else {}
  county = counties[0] if counties else {}
  return {
    'place_name': place.get('BASENAME') or None,
    'place_geoid': place.get('GEOID') or None,
    'county_name': county.get('BASENAME') or None,
    'county_fips': county.get('GEOID') or None,
  }


def geographies_for_point(lat: float, lng: float, session: Optional[requests.Session] = None) -> Optional[Dict[str, Optional[str]]]:
  """Political containment of a coordinate: incorporated place + county.

  @param lat @param lng The point, EPSG:4326.
  @param session Optional requests.Session for connection reuse.

  @return {'place_name', 'place_geoid', 'county_name', 'county_fips'} — with
    place_name None for unincorporated territory — or None on transport
    failure (retried once first).
  """
  http = session or requests
  params = {
    'x': lng,
    'y': lat,
    'benchmark': _BENCHMARK,
    'vintage': _VINTAGE,
    'layers': _LAYERS,
    'format': 'json',
  }
  for attempt in range(_ATTEMPTS):
    if attempt:
      time.sleep(_RETRY_PAUSE_SECONDS)
    try:
      response = http.get(_COORDINATES_URL, params=params, timeout=_TIMEOUT_SECONDS)
    except Exception as error:
      _log_error('census: geographies request threw for (%s, %s): %s' % (lat, lng, error))
      continue
    if not response.ok:
      _log_error('census: geographies failed for (%s, %s) (status %s)' % (lat, lng, response.status_code))
      continue
    try:
      payload = response.json()
    except Exception as error:
      _log_error('census: bad JSON from geographies for (%s, %s): %s' % (lat, lng, error))
      continue
    geographies = ((payload.get('result') or {}).get('geographies'))
    if geographies is not None:
      return _extract_geographies(geographies)
  return None
