"""
compare.py
----------
Phase D of the front-edge QA: put our labels and FutureLot's side by side.

Both systems answer the same question about the same polygon — which edge of
this corner lot is the front — so the comparison is geometric, not textual:
every FutureLot edge is matched to the engine edge it physically is (midpoint
within tolerance, near-parallel bearing), and only then are the two labels
compared. That survives the fact that the two polygons are not vertex-for-vertex
identical: FutureLot serves a simplified lot, and our engine merges collinear
runs into single edges and splits a frontage where a neighbour interrupts it.

Before any of that it checks the two are even talking about the same parcel —
centroid within LOT_MATCH_FT and comparable area — because an address that
resolves to a different lot on their side is a finding of its own, not a
labeling difference.

Verdicts (the front is what matters; rear/side agreement is reported as
context):

  agree              — same single edge is the front on both sides
  futurelot_extra_front — FutureLot calls our front a front AND calls another
                       street edge a front too (dual-front corner treatment)
  engine_extra_front — the reverse: our all_fronts rule marks a second front
                       FutureLot does not
  different_front    — FutureLot's front is an edge we did not call front
  no_front           — one side produced no front edge at all

  python3 qa/front-edge/compare.py

Writes out/report.md, out/report.csv and data/comparison.json.
"""
import csv
import json
import math
import os
import re

from qa_common import DATA_DIR, OUT_DIR, angle_between, edge_bearing_deg, edge_midpoint, read_json, write_json

FT_PER_DEG_LAT = 364_000.0
# Edge-match tolerances. A frontage split by the engine still has its midpoint
# within a few tens of feet of the simplified edge's midpoint; anything further
# is a different edge, not the same one described differently.
EDGE_MATCH_FT = 60.0
EDGE_MATCH_ANGLE_DEG = 30.0
# Same-parcel check: two renderings of one lot agree on their centroid far more
# tightly than neighbouring lots are apart.
LOT_MATCH_FT = 60.0

# County assessors and FutureLot spell the same APN differently: dashes, leading
# zeros, a trailing check digit (Contra Costa) or trailing '000' (Sonoma, Napa).
# Normalize and accept a prefix match rather than call the same parcel two lots.
_APN_MIN_PREFIX = 7


def _apn_key(apn):
  return re.sub(r'[^0-9a-z]', '', (apn or '').lower()).lstrip('0')


def apns_match(ours, theirs):
  a, b = _apn_key(ours), _apn_key(theirs)
  if not a or not b:
    return None
  if a == b:
    return True
  short, long_ = (a, b) if len(a) <= len(b) else (b, a)
  return len(short) >= _APN_MIN_PREFIX and long_.startswith(short)


# The two sides can agree on the parcel and still disagree about its SHAPE —
# the county fabric and FutureLot's source are different polygons. That is a
# different finding from a labeling difference, so it is measured separately.
AREA_MISMATCH_RATIO = 0.15


# FutureLot's vocabulary -> ours. It has no 'street_side': a corner's second
# street frontage is either 'front' (dual-front reading) or 'side'.
FL_TAGS = {'front': 'front', 'rear': 'rear', 'side': 'side'}

# Counting edges labelled 'front' overstates the answer: FutureLot serves a lot
# whose street face is often split into several collinear segments plus a corner
# clip, so one frontage can arrive as four 'front' edges. What both systems are
# really asserting is a number of FRONTAGES — runs of street face pointing the
# same way — so edges are grouped by bearing before anything is compared.
FRONTAGE_GROUP_ANGLE_DEG = 25.0
# A run shorter than this is a corner clip or a driveway notch, not a frontage.
MIN_FRONTAGE_FT = 20.0


def _distance_ft(a, b):
  scale = math.cos(math.radians((a[1] + b[1]) / 2))
  return math.hypot((a[0] - b[0]) * scale, a[1] - b[1]) * FT_PER_DEG_LAT


def _centroid(ring):
  pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
  return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def _ring_area_sqft(ring):
  """Shoelace on a local equirectangular projection."""
  lat0 = sum(p[1] for p in ring) / len(ring)
  scale = math.cos(math.radians(lat0))
  total = 0.0
  for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
    total += (x1 * scale) * y2 - (x2 * scale) * y1
  return abs(total) / 2.0 * (FT_PER_DEG_LAT ** 2)


def _engine_edges(record):
  out = []
  for index, edge in enumerate(record['labeled']['edges']):
    out.append({
      'index': index,
      'tag': edge['tag'],
      'street_name': (edge['abuts'] or {}).get('streetName'),
      'abuts': (edge['abuts'] or {}).get('kind'),
      'length_ft': round(edge['lengthFt'], 1),
      'flags': edge['flags'],
      'mid': list(edge_midpoint(edge['pts'])),
      'bearing': edge_bearing_deg(edge['pts']),
      'pts': [list(p) for p in edge['pts']],
    })
  return out


def _futurelot_edges(observation):
  out = []
  for index, edge in enumerate(observation.get('edges') or []):
    vertexes = edge.get('v') or []
    if len(vertexes) < 2:
      continue
    out.append({
      'index': index,
      'tag': FL_TAGS.get((edge.get('type') or '').lower(), (edge.get('type') or '').lower()),
      'raw_type': edge.get('type'),
      'length_ft': edge.get('len'),
      'mid': list(edge_midpoint(vertexes)),
      'bearing': edge_bearing_deg(vertexes),
      'pts': [list(p) for p in vertexes],
    })
  return out


def _frontage_groups(edges):
  """Cluster edges into frontages by bearing; return [(bearing, total_ft, count)]
  for the runs long enough to be a street face."""
  groups = []
  for edge in edges:
    for group in groups:
      if angle_between(group['bearing'], edge['bearing']) <= FRONTAGE_GROUP_ANGLE_DEG:
        group['length_ft'] += edge['length_ft'] or 0
        group['count'] += 1
        break
    else:
      groups.append({'bearing': edge['bearing'], 'length_ft': edge['length_ft'] or 0, 'count': 1})
  return [{'bearing_deg': round(g['bearing'], 1), 'length_ft': round(g['length_ft'], 1),
           'edges': g['count']}
          for g in groups if g['length_ft'] >= MIN_FRONTAGE_FT]


def _point_to_segment_ft(point, a, b):
  """Distance from a point to a segment, in feet, on a local flat projection."""
  scale = math.cos(math.radians(point[1]))
  px, py = point[0] * scale, point[1]
  ax, ay = a[0] * scale, a[1]
  bx, by = b[0] * scale, b[1]
  dx, dy = bx - ax, by - ay
  span = dx * dx + dy * dy
  t = 0.0 if span == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
  return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * FT_PER_DEG_LAT


def _point_to_polyline_ft(point, pts):
  return min(_point_to_segment_ft(point, a, b) for a, b in zip(pts, pts[1:]))


def _match(source_edges, target_edges):
  """For each source edge, the target edge that physically is it (or None).

  Distance is from the source edge's midpoint to the target edge's *line*, not
  to its midpoint: the two systems split the same street face differently — one
  serves a 100 ft side where the other serves 76 ft + 36 ft — and midpoint-to-
  midpoint would score those as different edges when they lie on top of each
  other.
  """
  pairs = []
  for source in source_edges:
    best, best_distance = None, None
    for target in target_edges:
      if angle_between(source['bearing'], target['bearing']) > EDGE_MATCH_ANGLE_DEG:
        continue
      distance = _point_to_polyline_ft(source['mid'], target['pts'])
      if distance <= EDGE_MATCH_FT and (best_distance is None or distance < best_distance):
        best, best_distance = target, distance
    pairs.append((source, best, None if best is None else round(best_distance, 1)))
  return pairs


def compare_one(jurisdiction, engine_record, observation):
  result = {'jurisdiction': jurisdiction}
  if engine_record is None:
    return dict(result, verdict='no_engine_result')
  if observation is None or observation.get('status') != 200:
    return dict(result, verdict='no_futurelot_result',
                futurelot_status=(observation or {}).get('status'),
                futurelot_error=(observation or {}).get('error') or (observation or {}).get('body'))

  ours = _engine_edges(engine_record)
  theirs = _futurelot_edges(observation)
  resolved = engine_record['resolved']
  result['address'] = engine_record['query_address']
  result['apn'] = resolved['apn']
  result['front_rule'] = engine_record['front_rule']['rule']
  result['zone'] = (resolved.get('zone') or {}).get('zone_code')
  result['engine_used'] = engine_record.get('used')

  # Same parcel?
  lot_rings = observation.get('lot') or []
  their_ring = lot_rings[0] if lot_rings else None
  if their_ring:
    their_centroid = _centroid(their_ring)
    our_centroid = [resolved['lng'], resolved['lat']]
    result['lot_centroid_offset_ft'] = round(_distance_ft(our_centroid, their_centroid), 1)
    result['futurelot_area_sqft'] = round(_ring_area_sqft(their_ring))
    result['same_lot'] = result['lot_centroid_offset_ft'] <= LOT_MATCH_FT
  else:
    result['same_lot'] = None

  attributes = observation.get('attributes') or {}
  result['futurelot_apn'] = attributes.get('parcel_id')
  result['apn_match_futurelot'] = apns_match(resolved['apn'], attributes.get('parcel_id'))
  result['futurelot_property_id'] = attributes.get('property_id')
  result['futurelot_zone'] = attributes.get('zone_code')
  # Shape agreement, independent of labeling: area and edge count.
  their_area = attributes.get('lot_size') or result.get('futurelot_area_sqft')
  our_area = (engine_record.get('selected') or {}).get('area_sqft')
  if their_area and our_area:
    result['area_ratio'] = round(our_area / their_area, 3)
    result['lot_shape_mismatch'] = abs(result['area_ratio'] - 1.0) > AREA_MISMATCH_RATIO
  result['engine_edge_count'] = len(ours)
  result['futurelot_edge_count'] = len(theirs)

  our_fronts = [e for e in ours if e['tag'] == 'front']
  our_second_fronts = [e for e in ours if 'second_front' in e['flags']]
  their_fronts = [e for e in theirs if e['tag'] == 'front']
  our_front_groups = _frontage_groups(our_fronts + our_second_fronts)
  their_front_groups = _frontage_groups(their_fronts)
  result['engine_front_count'] = len(our_front_groups)
  result['futurelot_front_count'] = len(their_front_groups)
  result['engine_front_groups'] = our_front_groups
  result['futurelot_front_groups'] = their_front_groups
  result['futurelot_front_edge_count'] = len(their_fronts)
  result['engine_front_street'] = our_fronts[0]['street_name'] if our_fronts else None
  result['engine_street_names'] = engine_record['analysis']['street_names']

  # Match every FutureLot edge onto ours and vice versa.
  pairs = _match(theirs, ours)
  result['edges'] = [{
    'futurelot': their['raw_type'], 'futurelot_len_ft': their['length_ft'],
    'engine': None if mine is None else mine['tag'],
    'engine_street': None if mine is None else mine['street_name'],
    'engine_abuts': None if mine is None else mine['abuts'],
    'engine_len_ft': None if mine is None else mine['length_ft'],
    'engine_flags': None if mine is None else mine['flags'],
    'midpoint_offset_ft': distance,
  } for their, mine, distance in pairs]

  matched_to_our_front = [p for p in pairs if p[1] is not None and p[1]['tag'] == 'front']
  their_label_on_our_front = sorted({p[0]['tag'] for p in matched_to_our_front})
  result['futurelot_label_on_engine_front'] = their_label_on_our_front

  # Verdict.
  if not our_fronts or not their_fronts:
    verdict = 'no_front'
  elif 'front' not in their_label_on_our_front:
    verdict = 'different_front'
  elif result['futurelot_front_count'] > result['engine_front_count']:
    verdict = 'futurelot_extra_front'
  elif result['engine_front_count'] > result['futurelot_front_count']:
    verdict = 'engine_extra_front'
  else:
    verdict = 'agree'
  result['verdict'] = verdict

  # Secondary: how the non-front edges line up.
  agreements = 0
  comparable = 0
  for their, mine, _ in pairs:
    if mine is None:
      continue
    comparable += 1
    # street_side is FutureLot's 'side' or 'front' depending on its corner
    # reading; count only the tags that mean the same thing in both.
    if their['tag'] == mine['tag']:
      agreements += 1
  result['edge_tag_agreement'] = '%d/%d' % (agreements, comparable)
  # An edge of theirs with no counterpart of ours means the two sources disagree
  # about the polygon itself, not about its labels — area alone misses that, since
  # a triangle and a rectangle can have the same area. Short edges are excluded:
  # our engine merges corner clips and collinear runs by design, so an unmatched
  # 17 ft clip is our simplification working, not a disagreement.
  unmatched = [s_ for s_, mine, _ in pairs if mine is None]
  result['unmatched_futurelot_edges'] = len(unmatched)
  result['unmatched_futurelot_edges_significant'] = sum(
    1 for e in unmatched if (e['length_ft'] or 0) >= MIN_FRONTAGE_FT)
  result['geometry_disagreement'] = result['unmatched_futurelot_edges_significant'] > 0
  result['adu_setbacks_futurelot'] = (observation.get('adu_setbacks') or {}).get('ext')
  result['lot_flags'] = engine_record['analysis']['lot_flags']
  # Our own known defect on this lot, so the report can attribute a mismatch
  # to it rather than to FutureLot.
  result['roads_collapsed_frontage'] = bool(engine_record.get('roads_collapsed_frontage'))
  result['engine_street_names_census'] = (engine_record.get('analysis_census') or {}).get('street_names')
  return result


VERDICT_ORDER = ['different_front', 'futurelot_extra_front', 'engine_extra_front', 'agree',
                 'no_front', 'no_futurelot_result', 'no_engine_result']


def main():
  engine = read_json(os.path.join(DATA_DIR, 'engine_results.json'), {}) or {}
  observations = {o['jurisdiction']: o
                  for o in (read_json(os.path.join(DATA_DIR, 'futurelot_observations.json'), []) or [])}
  jurisdictions = [j['jurisdiction'] for j in
                   read_json(os.path.join(os.path.dirname(DATA_DIR), '..', '..', 'zoning-ordinances',
                                          'zoning_ordinance_links.json'), {}).get('jurisdictions', [])]
  jurisdictions = jurisdictions or sorted(set(engine) | set(observations))

  rows = [compare_one(j, engine.get(j), observations.get(j)) for j in jurisdictions]
  write_json(os.path.join(DATA_DIR, 'comparison.json'), rows)

  os.makedirs(OUT_DIR, exist_ok=True)
  fields = ['jurisdiction', 'front_rule', 'address', 'apn', 'futurelot_apn', 'apn_match_futurelot',
            'zone', 'same_lot', 'lot_shape_mismatch', 'area_ratio',
            'engine_front_street', 'engine_front_count', 'futurelot_front_count',
            'futurelot_label_on_engine_front', 'verdict', 'roads_collapsed_frontage',
            'edge_tag_agreement', 'lot_flags']
  with open(os.path.join(OUT_DIR, 'report.csv'), 'w', newline='', encoding='utf-8') as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
      writer.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                       for k, v in row.items() if k in fields})

  counts = {}
  for row in rows:
    counts[row['verdict']] = counts.get(row['verdict'], 0) + 1

  lines = ['# Front-edge QA: engine vs FutureLot', '',
           'One corner lot per jurisdiction. "Front" is the edge each system calls the',
           'primary front lot line; edges are matched geometrically before their labels',
           'are compared.', '', '## Verdicts', '']
  for verdict in VERDICT_ORDER:
    if counts.get(verdict):
      lines.append('- **%s** — %d' % (verdict, counts[verdict]))
  lines += ['', '## Cross-checks', '',
            'Before the labels are compared at all: are the two sides describing the',
            'same parcel, and the same polygon?', '',
            '- APN agreement (engine vs FutureLot `parcel_id`): **%d / %d**' % (
              sum(1 for r in rows if r.get('apn_match_futurelot')), len(rows)),
            '- Lot area within %d%%: **%d / %d**' % (
              int(AREA_MISMATCH_RATIO * 100),
              sum(1 for r in rows if r.get('lot_shape_mismatch') is False), len(rows)),
            '- Every FutureLot edge matched to one of ours: **%d / %d**' % (
              sum(1 for r in rows if r.get('geometry_disagreement') is False), len(rows)),
            '- Lots where our Roads namer merged two frontages into one: **%d**  '
            '(our defect, not a FutureLot difference)' % sum(
              1 for r in rows if r.get('roads_collapsed_frontage')), '',
            '## Per jurisdiction', '',
            '| Jurisdiction | Front rule | Lot | Engine front | Fronts (engine / FL) '
            '| FL label on our front | Verdict | Notes |',
            '|---|---|---|---|---|---|---|---|']
  for row in rows:
    notes = []
    if row.get('roads_collapsed_frontage'):
      notes.append('roads collapsed frontage')
    if row.get('geometry_disagreement'):
      notes.append('%d FL edge(s) unmatched' % row.get('unmatched_futurelot_edges_significant', 0))
    if row.get('lot_shape_mismatch'):
      notes.append('area x%s' % row.get('area_ratio'))
    if row.get('apn_match_futurelot') is False:
      notes.append('APN mismatch')
    lines.append('| %s | %s | %s | %s | %s / %s | %s | %s | %s |' % (
      row['jurisdiction'], row.get('front_rule') or '—',
      row.get('address') or '—', row.get('engine_front_street') or '—',
      row.get('engine_front_count', '—'), row.get('futurelot_front_count', '—'),
      ', '.join(row.get('futurelot_label_on_engine_front') or []) or '—',
      row['verdict'], '; '.join(notes) or '—'))
  lines += ['', '## Edge detail', '']
  for row in rows:
    if not row.get('edges'):
      continue
    lines += ['### %s — %s' % (row['jurisdiction'], row.get('address')),
              '',
              'rule `%s` · zone `%s` · same lot: %s (centroid offset %s ft)' % (
                row.get('front_rule'), row.get('zone'), row.get('same_lot'),
                row.get('lot_centroid_offset_ft')),
              '',
              '| FutureLot | ft | Engine | street | abuts | ft | offset ft |',
              '|---|---|---|---|---|---|---|']
    for edge in row['edges']:
      lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (
        edge['futurelot'], edge['futurelot_len_ft'], edge['engine'] or '(unmatched)',
        edge['engine_street'] or '—', edge['engine_abuts'] or '—',
        edge['engine_len_ft'] if edge['engine_len_ft'] is not None else '—',
        edge['midpoint_offset_ft'] if edge['midpoint_offset_ft'] is not None else '—'))
    lines.append('')

  with open(os.path.join(OUT_DIR, 'report.md'), 'w', encoding='utf-8') as handle:
    handle.write('\n'.join(lines) + '\n')
  print('\n'.join('%-24s %d' % (v, c) for v, c in sorted(counts.items(), key=lambda kv: -kv[1])))
  print('\nwrote out/report.md, out/report.csv, data/comparison.json')


if __name__ == '__main__':
  main()
