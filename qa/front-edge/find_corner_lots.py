"""
find_corner_lots.py
-------------------
Phase A of the front-edge QA: find one corner lot per jurisdiction.

The search runs on the same parcel fabric the production provider uses. Per
jurisdiction it geocodes a seed, pulls ONE envelope of county parcels around
it, and then re-runs the labeling engine locally over every parcel in that
envelope — each parcel as subject, and as its fabric exactly the neighbour set
the provider would have fetched for it (see _neighbors_like_production; getting
this wrong makes discovery report corners that stop being corners the moment
production re-labels them) — keeping the ones the engine sees as having two
non-parallel street frontages. That is
the definition of a corner lot that matters here: not "the assessor says
corner" but "our engine believes two streets meet at this lot", which is
exactly the condition the jurisdiction front rule exists to resolve.

Discovery is census-only (no Google Roads calls): street *names* do not decide
corner-ness, geometry does, and the canonical run in run_engine.py turns the
Roads namer back on. The one Google call per jurisdiction is the seed geocode,
and it is cached on disk.

Candidates are then ranked (ordinary residential size, a real house-numbered
situs, two named streets) and the top few are confirmed against the Census
place lookup, so the lot we hand to FutureLot is provably inside the
jurisdiction whose rule we are testing — including the unincorporated cases,
where the postal city name lies.

  python3 qa/front-edge/find_corner_lots.py [--jurisdiction NAME] [--limit N]

Writes data/candidates.json (everything found) and data/selected.json (the one
lot per jurisdiction the rest of the harness uses).
"""
import argparse
import math
import os
import re
import sys

from county_overrides import county_layer_for
from shapely import wkt as shapely_wkt

from qa_common import (
  DATA_DIR, QA_DIR, SESSION, analyze, geocode, parcel_area_sqft, read_json, run_labeling, write_json,
)
from services.parcel_data.arcgis_parcel_client import attach_joined_situs, fetch_parcels_in_envelope
from services.parcel_data.ca_zoning_client import fetch_zone_at_point
from services.parcel_data.census_geocoder_client import geographies_for_point
from services.parcel_data.county_registry import county_for_name
from services.parcel_data.fetch_parcel_context import DEFAULT_MAX_NEIGHBORS
from services.parcel_data.front_rules import front_rule_for, load_jurisdictions

# Half-size of the fabric envelope around a seed. 200 m of a residential grid is
# a few blocks — enough to contain several intersections — while staying under
# the client's 200-record envelope cap.
ENVELOPE_HALF_M = 200.0
ENVELOPE_GROW = [1.0, 1.75, 3.0]
M_PER_DEG_LAT = 111_320.0
# Mirror the provider's own neighbour window (fetch_parcel_context:
# DEFAULT_MAX_NEIGHBORS, DEFAULT_MARGIN_M) so a lot that looks like a corner
# during discovery still looks like one when production re-labels it.
NEIGHBORS_PER_CANDIDATE = DEFAULT_MAX_NEIGHBORS
DEFAULT_MARGIN_M = 15.0

# An ordinary single-family lot. Both ends matter: postage stamps and estates
# both exist on corners, but the mid-range is where a jurisdiction's ADU
# setback rule is actually argued.
AREA_MIN_SQFT = 3_000
AREA_MAX_SQFT = 30_000

_HOUSE_NUMBER = re.compile(r'^\s*\d+')

# The statewide zoning layer carries each jurisdiction's own vocabulary: the
# 'Description' is often just the code again ('R-6', '3-DUA', 'RL-20'), so a
# search for the word "residential" would throw away most of Contra Costa and
# Marin. Reject only on a positive non-residential signal; treat everything
# else as unknown, and let the positive patterns break ties.
_NON_RESIDENTIAL = re.compile(
  r'commercial|industrial|\boffice|retail|business|institution|manufactur|'
  r'public facilit|open space|\bpark\b|agricultur|school|hospital|airport|utility',
  re.I)
# Codes whose description is just the code again. Kept to the unambiguous
# commercial/industrial prefixes — CN and CP (Santa Clara County's Neighborhood
# and Pedestrian Commercial) are what put a strip of Bascom Ave in front of a
# residential search.
_NON_RESIDENTIAL_CODE = re.compile(r'^(c[-\s]?\d|c[cghnop]\b|m[-\s]?\d|i[-\s]?\d|ip\b|ig\b)', re.I)
_RESIDENTIAL = re.compile(
  r'resid|single fam|multi[- ]?fam|dwelling|\bdua\b|duplex'           # words
  r'|^r[a-z]{0,2}[- ]?\d|^r$|^r[- ]?e\b|^r[- ]?h\b',                  # code shapes: R-1, RS-6, RL-20, RD-5.5-7
  re.I)


def classify_residential(zone_code, zone_type):
  """True / False / None (unknown) for 'is this a residential district'."""
  text = ' '.join(t for t in [zone_code, zone_type] if t).strip()
  if not text:
    return None
  if _NON_RESIDENTIAL.search(text) or _NON_RESIDENTIAL_CODE.match((zone_code or '').strip()):
    return False
  if _RESIDENTIAL.search(zone_code or '') or _RESIDENTIAL.search(zone_type or ''):
    return True
  return None


def _deg_lng(meters, lat):
  return meters / (M_PER_DEG_LAT * max(0.1, math.cos(math.radians(lat))))


def _envelope(lat, lng, half_m):
  d_lat = half_m / M_PER_DEG_LAT
  d_lng = _deg_lng(half_m, lat)
  return lng - d_lng, lat - d_lat, lng + d_lng, lat + d_lat


def _distance_m(a_lat, a_lng, b_lat, b_lng):
  scale = math.cos(math.radians((a_lat + b_lat) / 2))
  return math.hypot((a_lng - b_lng) * scale, a_lat - b_lat) * M_PER_DEG_LAT


def _fabric(county, lat, lng):
  """Parcels around a seed, with situs attached for geometry-only fabrics."""
  for factor in ENVELOPE_GROW:
    xmin, ymin, xmax, ymax = _envelope(lat, lng, ENVELOPE_HALF_M * factor)
    parcels = fetch_parcels_in_envelope(county, xmin, ymin, xmax, ymax, session=SESSION)
    if parcels is None:
      print('    envelope query failed (factor %.2f)' % factor, file=sys.stderr)
      continue
    if county.get('situs_mode') == 'join' and parcels:
      # One batched join for the whole envelope, not per candidate.
      for chunk_start in range(0, len(parcels), 100):
        attach_joined_situs(county, parcels[chunk_start:chunk_start + 100], session=SESSION)
    if len(parcels) >= 20:
      return parcels, factor
  return (parcels or []), ENVELOPE_GROW[-1]


def _bounds(parcel):
  """Cached (xmin, ymin, xmax, ymax) — parsing every neighbour's WKT once per
  candidate turns an envelope scan quadratic in the fabric size."""
  cached = parcel.get('_bounds')
  if cached is None:
    cached = shapely_wkt.loads(parcel['boundary']).bounds
    parcel['_bounds'] = cached
  return cached


def _neighbors_like_production(subject, fabric):
  """The neighbour set fetch_parcel_context would have produced for this parcel.

  This has to mirror the provider exactly or discovery lies. Taking the twelve
  nearest centroids out of a wide fabric — the obvious thing — quietly drops
  abutters whose centroid is far (a deep or L-shaped neighbour) and leaves
  their shared edge looking like a street: six lots picked that way stopped
  being corners the moment the production path re-labelled them. The provider
  instead takes everything intersecting the subject's bounds plus a margin,
  then sorts by centroid distance and caps.
  """
  bounds = _bounds(subject)
  half_lng = _deg_lng(DEFAULT_MARGIN_M, subject['lat'])
  half_lat = DEFAULT_MARGIN_M / M_PER_DEG_LAT
  xmin, ymin = bounds[0] - half_lng, bounds[1] - half_lat
  xmax, ymax = bounds[2] + half_lng, bounds[3] + half_lat
  near = []
  for parcel in fabric:
    if parcel['apn'] == subject['apn']:
      continue
    p_bounds = _bounds(parcel)
    if p_bounds[2] < xmin or p_bounds[0] > xmax or p_bounds[3] < ymin or p_bounds[1] > ymax:
      continue
    near.append(parcel)
  near.sort(key=lambda p: _distance_m(subject['lat'], subject['lng'], p['lat'], p['lng']))
  return near[:NEIGHBORS_PER_CANDIDATE]


def _score(candidate):
  """Rank corner lots by how good a QA specimen they are (higher is better)."""
  score = 0.0
  if len(candidate['analysis']['street_names']) >= 2:
    score += 40                      # two named streets: the comparison is legible
  elif candidate['analysis']['street_names']:
    score += 10
  if _HOUSE_NUMBER.match(candidate['address'] or ''):
    score += 30                      # FutureLot needs a street address to look up
  angle = candidate['analysis']['max_frontage_angle_deg']
  score += 20 * min(1.0, angle / 70.0)   # nearer a right angle = less ambiguous corner
  area = candidate['area_sqft']
  if AREA_MIN_SQFT <= area <= AREA_MAX_SQFT:
    score += 20
  if candidate['analysis']['street_frontage_count'] == 2:
    score += 10                      # a plain corner, not a triple frontage
  if 'no_street_frontage' in candidate['analysis']['lot_flags']:
    score -= 50
  if 'through_lot' in candidate['analysis']['lot_flags']:
    score -= 40
  score -= 5 * len(candidate['analysis']['lot_flags'])
  return round(score, 1)


def _candidates_near(county, lat, lng, front_rule, jurisdiction):
  parcels, factor = _fabric(county, lat, lng)
  print('    fabric: %d parcels (envelope x%.2f)' % (len(parcels), factor))
  found = []
  for subject in parcels:
    try:
      area = parcel_area_sqft(subject['boundary'])
    except Exception:
      continue
    if not (AREA_MIN_SQFT * 0.5 <= area <= AREA_MAX_SQFT * 3):
      continue
    neighbors = _neighbors_like_production(subject, parcels)
    try:
      labeled = run_labeling(subject, neighbors, front_rule,
                             subject_street_name=None, use_roads_namer=False)
    except Exception as error:
      print('    label failed for %s: %s' % (subject['apn'], error), file=sys.stderr)
      continue
    analysis = analyze(labeled)
    if not analysis['is_corner']:
      continue
    candidate = {
      'jurisdiction': jurisdiction,
      'apn': subject['apn'],
      'address': subject.get('address') or '',
      'situs_city': subject.get('situs_city'),
      'lat': subject['lat'],
      'lng': subject['lng'],
      'area_sqft': round(area),
      'seed_distance_m': round(_distance_m(lat, lng, subject['lat'], subject['lng'])),
      'analysis': analysis,
    }
    candidate['score'] = _score(candidate)
    found.append(candidate)
  found.sort(key=lambda c: (-c['score'], c['seed_distance_m']))
  return found


def _confirms_jurisdiction(candidate, jurisdiction, county_name, require_residential=True):
  """Census point containment — the authority the pipeline itself trusts — plus a
  zoning check.

  The zoning check is not bureaucracy: the seeds aim at street grids, and the
  densest grids in a small city are its downtown. A commercial corner would
  test the front rule against a comparison tool that only reports on
  residential lots, so a non-residential district disqualifies the specimen.
  """
  geo = geographies_for_point(candidate['lat'], candidate['lng'], session=SESSION)
  if geo is None:
    return None, {'error': 'census_lookup_failed'}
  place = geo.get('place_name')
  resolved = front_rule_for(jurisdiction_name=place, county_name=geo.get('county_name'))
  detail = {'place_name': place, 'county_name': geo.get('county_name'),
            'county_fips': geo.get('county_fips'), 'rule_resolved': (resolved or {}).get('rule')}
  if jurisdiction.endswith('(unincorporated)'):
    ok = place is None and (geo.get('county_name') or '').startswith(county_name)
  else:
    ok = (place or '').lower() == jurisdiction.lower()

  zone = fetch_zone_at_point(candidate['lat'], candidate['lng'], session=SESSION) or {}
  detail['zone_code'] = zone.get('zone_code')
  detail['zone_type'] = zone.get('zone_type')
  detail['residential'] = classify_residential(zone.get('zone_code'), zone.get('zone_type'))
  if ok and require_residential and detail['residential'] is False:
    ok = False
    detail['rejected'] = 'not_residential'
  return ok, detail


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--jurisdiction', action='append', help='limit to these jurisdictions')
  parser.add_argument('--limit', type=int, default=6, help='candidates kept per jurisdiction')
  parser.add_argument('--confirm', type=int, default=8, help='top candidates put through the Census + zoning check')
  parser.add_argument('--allow-nonresidential', action='store_true',
                      help='accept a commercial/mixed-use corner when no residential one is found')
  args = parser.parse_args()

  seeds = {s['jurisdiction']: s['queries'] for s in read_json(os.path.join(QA_DIR, 'seeds.json'))['seeds']}
  records = {j['jurisdiction']: j for j in load_jurisdictions()}
  targets = args.jurisdiction or list(records.keys())

  all_candidates = read_json(os.path.join(DATA_DIR, 'candidates.json'), {}) or {}
  selected = read_json(os.path.join(DATA_DIR, 'selected.json'), {}) or {}

  for jurisdiction in targets:
    record = records.get(jurisdiction)
    if record is None:
      print('!! %s is not in the jurisdiction database' % jurisdiction, file=sys.stderr)
      continue
    county = county_for_name(record['county'])
    front_rule = record.get('front_rule') or {}
    print('== %s (%s County, rule=%s)' % (jurisdiction, record['county'], front_rule.get('rule')))

    chosen, pool = None, []
    with county_layer_for(jurisdiction) as overridden:
      if overridden:
        county = county_for_name(record['county'])
        print('    NOTE: QA parcel-layer override in effect (see county_overrides.py)')
      for query in seeds.get(jurisdiction, ['%s, CA' % jurisdiction]):
        point = geocode(query)
        if not point:
          print('    seed geocode failed: %s' % query, file=sys.stderr)
          continue
        print('    seed %r -> %.5f, %.5f' % (query, point['lat'], point['lng']))
        found = _candidates_near(county, point['lat'], point['lng'], front_rule, jurisdiction)
        for candidate in found:
          candidate['seed_query'] = query
          candidate['county_layer_override'] = overridden
        pool.extend(found)
        pool.sort(key=lambda c: (-c['score'], c['seed_distance_m']))
        # Confirm this seed's own best candidates, not the merged pool's: a
        # later seed's lots would otherwise sit forever behind higher-scoring
        # ones from an earlier seed that already failed confirmation.
        found.sort(key=lambda c: (-c['score'], c['seed_distance_m']))
        for candidate in found[:args.confirm]:
          if candidate.get('jurisdiction_check') is not None:
            continue
          ok, detail = _confirms_jurisdiction(candidate, jurisdiction, record['county'],
                                              require_residential=not args.allow_nonresidential)
          candidate['jurisdiction_check'] = detail
          candidate['jurisdiction_ok'] = bool(ok)
        confirmed = [c for c in found[:args.confirm] if c.get('jurisdiction_ok')]
        # A district we positively read as residential beats one we could not read.
        chosen = (next((c for c in confirmed if c['jurisdiction_check'].get('residential') is True), None)
                  or next(iter(confirmed), None))
        if chosen:
          break
        print('    no confirmed corner lot from this seed; trying the next', file=sys.stderr)

    all_candidates[jurisdiction] = pool[:args.limit]
    if chosen:
      print('    -> %s | %s | %s | %s | score %.1f' % (
        chosen['apn'], chosen['address'],
        ' + '.join(chosen['analysis']['street_names']) or '(unnamed)',
        chosen['jurisdiction_check'].get('zone_code') or '(no zone)', chosen['score']))
      selected[jurisdiction] = chosen
    else:
      print('    !! no confirmed corner lot found', file=sys.stderr)
      selected.pop(jurisdiction, None)
    write_json(os.path.join(DATA_DIR, 'candidates.json'), all_candidates)
    write_json(os.path.join(DATA_DIR, 'selected.json'), selected)

  print('\nselected %d / %d jurisdictions' % (len(selected), len(records)))


if __name__ == '__main__':
  main()
