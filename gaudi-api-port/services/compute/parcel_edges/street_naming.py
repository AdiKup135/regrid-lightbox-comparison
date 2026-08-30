"""
street_naming.py
----------------
Google Roads API as a street-naming source for parcel frontages.

The labeling pipeline can name a road gap two ways. The census reads the situs
addresses of neighbouring parcels — free, offline, but blind when the fabric has
no addresses or no neighbours. This module supplies the other way: ask Google
which road actually runs along a frontage.

Roads answers a question the census cannot ("what is this road called") but not
the one the parcel fabric answers ("does this lot line abut a right-of-way at
all"). It is therefore a naming source layered onto the pipeline, never a
replacement for it: ``edge_labeling`` decides which stretches are streets, then
asks this for their names and falls back to the census per section.

Cost shape, which is the reason this is batched the way it is:

* one ``nearestRoads`` request per parcel, carrying every frontage-section
  midpoint at once, rather than one request per edge;
* one Geocoding request per *distinct* ``placeId``, through a cache. Street
  names repeat across every parcel on a block, so a process-wide or shared cache
  drives this towards zero on the second lookup in a neighbourhood.

The namer is injected into ``label_edges`` rather than imported by it, so the
engine stays pure, offline-testable, and differentially comparable against the
reference implementation.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, MutableMapping, Optional, Sequence, Tuple

import requests

from .street_names import normalize_street_key

Pt = Tuple[float, float]  # (lng, lat), EPSG:4326

_ROADS_URL = "https://roads.googleapis.com/v1/nearestRoads"
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_TIMEOUT_SECONDS = 10

# Documented ceiling on points per nearestRoads request. Verify against current
# Google documentation before raising; requests are chunked to respect it.
_MAX_POINTS_PER_REQUEST = 100

# A snapped road further than this from the frontage midpoint is not this
# frontage's road. Without a ceiling, every edge of a lot snaps to *something* —
# a rear edge on a shallow lot snaps to the front street — and the result is a
# confident wrong answer.
DEFAULT_MAX_SNAP_FT = 60.0

_FT_PER_DEG_LAT = 364567.2


@dataclass(frozen=True)
class RoadName:
  """One road matched to one frontage point."""

  # Normalized comparable key, from street_names.normalize_street_key.
  key: str
  # The raw Google route name, for display and debugging.
  display: str
  # Distance from the queried point to the snapped road position.
  distance_ft: float
  place_id: str


# A namer takes frontage-section midpoints as (lng, lat) and returns one entry
# per input point, in order, None where no road could be attributed.
StreetNamer = Callable[[Sequence[Pt]], List[Optional[RoadName]]]


def _log(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request.

  Mirrors the fallback in sheets/zoneomics_client.py so this module is safe to
  call from a script or a test as well as from a Flask request.
  """
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def _distance_ft(a: Pt, b: Pt) -> float:
  """Planar distance between two nearby lng/lat points, in feet."""
  import math
  mid_lat = (a[1] + b[1]) / 2
  ft_per_deg_lng = _FT_PER_DEG_LAT * math.cos(math.radians(mid_lat))
  return math.hypot((a[0] - b[0]) * ft_per_deg_lng, (a[1] - b[1]) * _FT_PER_DEG_LAT)


def _nearest_roads(points: Sequence[Pt], api_key: str, session: requests.Session) -> Dict[int, Tuple[str, Pt]]:
  """Snap points to roads. Returns {input index: (place_id, snapped point)}.

  Keeps the nearest snap per input index — the API may return several snapped
  points for one input. Best-effort: any failure yields no attributions rather
  than raising, matching the rest of the Zoneomics/Google path.
  """
  best: Dict[int, Tuple[str, Pt]] = {}
  best_distance: Dict[int, float] = {}

  for start in range(0, len(points), _MAX_POINTS_PER_REQUEST):
    chunk = points[start:start + _MAX_POINTS_PER_REQUEST]
    # The Roads API takes lat,lng — the reverse of the lng,lat used everywhere else here.
    encoded = "|".join("%s,%s" % (lat, lng) for lng, lat in chunk)
    try:
      response = session.get(_ROADS_URL, params={"points": encoded, "key": api_key}, timeout=_TIMEOUT_SECONDS)
    except Exception as error:
      _log("roads: nearestRoads request threw: %s" % error)
      continue
    if not response.ok:
      _log("roads: nearestRoads failed (status %s)" % response.status_code)
      continue
    try:
      payload = response.json()
    except Exception as error:
      _log("roads: bad JSON from nearestRoads: %s" % error)
      continue

    for snapped in payload.get("snappedPoints") or []:
      original = snapped.get("originalIndex")
      location = snapped.get("location") or {}
      place_id = snapped.get("placeId")
      if original is None or not place_id:
        continue
      index = start + int(original)
      if not 0 <= index < len(points):
        continue
      position = (location.get("longitude"), location.get("latitude"))
      if position[0] is None or position[1] is None:
        continue
      distance = _distance_ft(points[index], position)
      if index not in best_distance or distance < best_distance[index]:
        best_distance[index] = distance
        best[index] = (place_id, position)
  return best


def _route_for_place_id(place_id: str, api_key: str, session: requests.Session,
                        cache: MutableMapping[str, Optional[str]]) -> Optional[str]:
  """Resolve a road placeId to its route name, through the cache."""
  if place_id in cache:
    return cache[place_id]
  route: Optional[str] = None
  try:
    response = session.get(_GEOCODE_URL, params={"place_id": place_id, "key": api_key}, timeout=_TIMEOUT_SECONDS)
    if response.ok:
      results = (response.json() or {}).get("results") or []
      components = results[0].get("address_components", []) if results else []
      for component in components:
        if "route" in (component.get("types") or []):
          route = component.get("long_name") or component.get("short_name")
          break
    else:
      _log("roads: geocode for placeId failed (status %s)" % response.status_code)
  except Exception as error:
    _log("roads: geocode for placeId threw: %s" % error)
  cache[place_id] = route
  return route


def make_google_roads_namer(api_key: str,
                            place_cache: Optional[MutableMapping[str, Optional[str]]] = None,
                            session: Optional[requests.Session] = None,
                            max_snap_ft: float = DEFAULT_MAX_SNAP_FT) -> StreetNamer:
  """Build a StreetNamer backed by the Google Roads and Geocoding APIs.

  @param api_key Google API key. Server-side only — never ship this to a browser.
  @param place_cache Mapping reused across calls for placeId -> route name. Pass
    a shared or persistent mapping to make repeat lookups on a block near-free.
  @param session Optional requests.Session for connection reuse.
  @param max_snap_ft Reject snaps further than this from the queried point.

  @return A callable taking (lng, lat) midpoints and returning one optional
    RoadName per point, in order.
  """
  cache: MutableMapping[str, Optional[str]] = {} if place_cache is None else place_cache
  http = session or requests.Session()

  def name_points(points: Sequence[Pt]) -> List[Optional[RoadName]]:
    out: List[Optional[RoadName]] = [None] * len(points)
    if not points or not api_key:
      return out

    snapped = _nearest_roads(points, api_key, http)
    if not snapped:
      return out

    # Resolve each DISTINCT placeId once, not once per point.
    for place_id in {pid for pid, _ in snapped.values()}:
      _route_for_place_id(place_id, api_key, http, cache)

    for index, (place_id, position) in snapped.items():
      distance = _distance_ft(points[index], position)
      if distance > max_snap_ft:
        continue
      route = cache.get(place_id)
      key = normalize_street_key(route)
      if not key:
        continue
      out[index] = RoadName(key=key, display=route or "", distance_ft=distance, place_id=place_id)
    return out

  return name_points
