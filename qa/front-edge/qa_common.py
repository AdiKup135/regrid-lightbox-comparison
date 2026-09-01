"""
qa_common.py
------------
Shared plumbing for the front-edge QA harness.

The harness is read-only with respect to the rest of the repo: it imports the
production-bound engine and provider out of ``gaudi-api-port/`` and the
jurisdiction database out of ``zoning-ordinances/``, and writes only inside
``qa/front-edge/``. Nothing here is part of the gaudi-api drop-in.

Everything the QA needs that is not already a public function of the pipeline
lives here: path bootstrapping, the shared HTTP session, an on-disk cache for
Google geocodes (so re-runs cost no quota), and the geometry helpers that turn
a labeling result into the two facts the comparison is about — *which street is
the front* and *is this actually a corner lot*.
"""
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

QA_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.normpath(os.path.join(QA_DIR, '..', '..'))
PORT_DIR = os.path.join(SITE_DIR, 'gaudi-api-port')
DATA_DIR = os.path.join(QA_DIR, 'data')
OUT_DIR = os.path.join(QA_DIR, 'out')

if PORT_DIR not in sys.path:
  sys.path.insert(0, PORT_DIR)

import requests  # noqa: E402
from shapely import wkt as shapely_wkt  # noqa: E402

from services.compute.parcel_edges.edge_labeling import (  # noqa: E402
  EdgeLabelingInput,
  FrontRuleOverride,
  ZoneomicsParcel,
  label_edges,
)
from services.parcel_data.front_rules import front_rule_for  # noqa: E402

SESSION = requests.Session()


# --- env ---------------------------------------------------------------------

def load_env() -> None:
  """Read site/.env into os.environ (only keys not already set)."""
  path = os.path.join(SITE_DIR, '.env')
  if not os.path.exists(path):
    return
  for line in open(path, encoding='utf-8'):
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
      continue
    key, value = line.split('=', 1)
    os.environ.setdefault(key.strip(), value.strip())


def google_key() -> Optional[str]:
  load_env()
  return (os.environ.get('GOOGLE_API_KEY') or '').strip() or None


# --- json io -----------------------------------------------------------------

def read_json(path: str, default: Any = None) -> Any:
  if not os.path.exists(path):
    return default
  with open(path, encoding='utf-8') as handle:
    return json.load(handle)


def write_json(path: str, payload: Any) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, indent=2, sort_keys=False)
    handle.write('\n')


# --- geocode cache -----------------------------------------------------------

_GEOCODE_CACHE_PATH = os.path.join(DATA_DIR, 'geocode_cache.json')


def geocode(query: str) -> Optional[Dict[str, float]]:
  """Google Geocoding with an on-disk cache — a re-run of the QA spends no quota."""
  cache = read_json(_GEOCODE_CACHE_PATH, {}) or {}
  if query in cache:
    return cache[query]
  key = google_key()
  if not key:
    return None
  response = SESSION.get('https://maps.googleapis.com/maps/api/geocode/json',
                         params={'address': query, 'key': key}, timeout=20)
  payload = response.json() if response.ok else {}
  results = payload.get('results') or []
  hit = None
  if results:
    location = results[0]['geometry']['location']
    hit = {'lat': location['lat'], 'lng': location['lng'],
           'formatted_address': results[0].get('formatted_address')}
  cache[query] = hit
  write_json(_GEOCODE_CACHE_PATH, cache)
  return hit


# --- geometry ----------------------------------------------------------------

FT_PER_M = 3.280839895


def parcel_area_sqft(boundary_wkt: str) -> float:
  """Planar area of a lng/lat polygon via a local equirectangular projection."""
  geometry = shapely_wkt.loads(boundary_wkt)
  lat0 = geometry.centroid.y
  scale = math.cos(math.radians(lat0))
  # deg -> m, then m^2 -> ft^2.
  return geometry.area * (111_320.0 ** 2) * scale * (FT_PER_M ** 2)


def edge_bearing_deg(pts: List[List[float]]) -> float:
  """Compass-ish bearing of an edge's chord, folded to [0, 180) — direction is
  irrelevant for 'are these two frontages perpendicular'."""
  (x1, y1), (x2, y2) = pts[0], pts[-1]
  scale = math.cos(math.radians((y1 + y2) / 2))
  angle = math.degrees(math.atan2(y2 - y1, (x2 - x1) * scale))
  return angle % 180.0


def angle_between(a_deg: float, b_deg: float) -> float:
  """Smallest angle between two undirected bearings, in [0, 90]."""
  d = abs(a_deg - b_deg) % 180.0
  return min(d, 180.0 - d)


def edge_midpoint(pts: List[List[float]]) -> Tuple[float, float]:
  """Midpoint of an edge by arc length — the point to drop on a map to show
  which frontage the engine called the front."""
  total = 0.0
  spans = []
  for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
    scale = math.cos(math.radians((y1 + y2) / 2))
    length = math.hypot((x2 - x1) * scale, y2 - y1)
    spans.append(length)
    total += length
  if total <= 0:
    return pts[0][0], pts[0][1]
  target, walked = total / 2.0, 0.0
  for span, (a, b) in zip(spans, zip(pts, pts[1:])):
    if walked + span >= target:
      t = (target - walked) / span if span else 0.0
      return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    walked += span
  return pts[-1][0], pts[-1][1]


# --- labeling ----------------------------------------------------------------

def to_parcel(record: Dict[str, Any]) -> ZoneomicsParcel:
  return ZoneomicsParcel(
    apn=str(record.get('apn', '')),
    address=record.get('address') or '',
    lat=float(record['lat']),
    lng=float(record['lng']),
    boundary=record['boundary'],
  )


def run_labeling(subject: Dict[str, Any], neighbors: List[Dict[str, Any]],
                 front_rule: Optional[Dict[str, Any]], zone: Optional[Dict[str, Any]] = None,
                 subject_street_name: Optional[str] = None,
                 use_roads_namer: bool = False) -> Dict[str, Any]:
  """label_edges over the wire-shape records — the same assembly routes/cli use.

  @param use_roads_namer True spends one Google Roads call (plus geocodes per
    distinct placeId) per lookup. Discovery runs census-only; the canonical
    per-jurisdiction run turns it on, because that is what production does.
  """
  front_rule = front_rule or {}
  namer = None
  if use_roads_namer:
    key = google_key()
    if key:
      from services.compute.parcel_edges.street_naming import make_google_roads_namer
      namer = make_google_roads_namer(key)
  overrides = [FrontRuleOverride.from_db(o) for o in front_rule.get('overrides') or []]
  result = label_edges(EdgeLabelingInput(
    subject=to_parcel(subject),
    neighbors=[to_parcel(n) for n in neighbors],
    front_rule=front_rule.get('rule'),
    front_rule_overrides=overrides or None,
    zone=zone,
    subject_street_name=subject_street_name,
    street_namer=namer,
  ))
  return result.to_dict()


# --- corner-lot analysis -----------------------------------------------------

# Two street frontages this far off parallel are an intersection corner rather
# than the two ends of a through lot. The engine has its own through_lot flag;
# this is the geometric cross-check, and it is what makes a lot QA-worthy: a
# through lot exercises a different branch of the rules than a corner.
CORNER_MIN_ANGLE_DEG = 25.0
# Below this a "frontage" is a corner clip or a driveway notch, not a street face.
MIN_FRONTAGE_FT = 15.0


def analyze(labeled: Dict[str, Any]) -> Dict[str, Any]:
  """Reduce a labeling result to the facts the FutureLot comparison turns on."""
  edges = labeled['edges']
  street_edges = [e for e in edges if (e['abuts'] or {}).get('kind') == 'street'
                  and e['lengthFt'] >= MIN_FRONTAGE_FT]
  names = []
  for e in street_edges:
    name = (e['abuts'] or {}).get('streetName')
    if name and name not in names:
      names.append(name)
  bearings = [edge_bearing_deg(e['pts']) for e in street_edges]
  max_angle = 0.0
  for i in range(len(bearings)):
    for j in range(i + 1, len(bearings)):
      max_angle = max(max_angle, angle_between(bearings[i], bearings[j]))

  front = next((e for e in edges if e['tag'] == 'front'), None)
  street_sides = [e for e in edges if e['tag'] == 'street_side']
  return {
    'is_corner': len(street_edges) >= 2 and max_angle >= CORNER_MIN_ANGLE_DEG,
    'street_frontage_count': len(street_edges),
    'street_names': names,
    'max_frontage_angle_deg': round(max_angle, 1),
    'front': None if front is None else {
      'street_name': (front['abuts'] or {}).get('streetName'),
      'street_name_source': (front['abuts'] or {}).get('streetNameSource'),
      'length_ft': round(front['lengthFt'], 1),
      'bearing_deg': round(edge_bearing_deg(front['pts']), 1),
      'midpoint': [round(v, 6) for v in edge_midpoint(front['pts'])],
      'basis': front['basis'],
      'confidence': front['confidence'],
      'flags': front['flags'],
    },
    'street_sides': [{
      'street_name': (e['abuts'] or {}).get('streetName'),
      'length_ft': round(e['lengthFt'], 1),
      'bearing_deg': round(edge_bearing_deg(e['pts']), 1),
      'midpoint': [round(v, 6) for v in edge_midpoint(e['pts'])],
      'flags': e['flags'],
    } for e in street_sides],
    'tags': [e['tag'] for e in edges],
    'lot_flags': labeled['flags'],
  }
