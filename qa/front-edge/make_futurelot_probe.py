"""
make_futurelot_probe.py
-----------------------
Phase C, part 1: emit the browser probe that reads FutureLot's own answers.

FutureLot's report page is a React app whose lot geometry arrives from a
same-origin Next.js route, ``/api/street-data``, keyed by address parts plus a
coordinate. Its ``lot_simplified.lot_edges`` is the directly comparable
artifact: one entry per lot edge with ``vertexes`` and an ``edge_type`` of
front / rear / side — the same decision our engine makes, from the same corner
lot. Reading that beats screen-scraping the map: it is the numbers behind the
labels, not a picture of them.

This script prints a self-contained JavaScript program to stdout. Run it in a
tab that is already signed in to app.futurelot.com (the QA is a comparison
against what the product actually shows this account) and save the JSON it
returns to data/futurelot_observations.json. Requests are issued one at a time
with a pause; nothing is written, submitted, or purchased — this is the same
GET the page makes when you open a report.

  python3 qa/front-edge/make_futurelot_probe.py > out/probe.js
"""
import json
import os
import re

from shapely import wkt as shapely_wkt

from qa_common import DATA_DIR, read_json

_SUFFIX_EXPANSIONS = {
  'AV': 'avenue', 'AVE': 'avenue', 'ST': 'street', 'RD': 'road', 'DR': 'drive',
  'LN': 'lane', 'CT': 'court', 'CIR': 'circle', 'BLVD': 'boulevard', 'PL': 'place',
  'WY': 'way', 'WAY': 'way', 'TER': 'terrace', 'PKWY': 'parkway', 'HWY': 'highway',
  'PATH': 'path', 'PLZ': 'plaza', 'TRL': 'trail', 'SQ': 'square', 'ALY': 'alley',
}


def split_situs(situs):
  """'589 COLERIDGE AV' -> ('589', 'coleridge avenue').

  FutureLot's route wants the house number and the street separately, with the
  suffix spelled out the way its own URLs spell it (Coleridge-Avenue). Only the
  trailing token is expanded; a street whose name contains a suffix word
  ('Park Avenue Court') keeps its interior tokens.
  """
  tokens = [t for t in re.split(r'\s+', (situs or '').strip()) if t]
  if not tokens:
    return '', ''
  number, rest = '', tokens
  if re.match(r'^\d+[A-Za-z]?$', tokens[0]):
    number, rest = tokens[0], tokens[1:]
  if rest:
    last = rest[-1].upper().strip('.')
    if last in _SUFFIX_EXPANSIONS:
      rest = rest[:-1] + [_SUFFIX_EXPANSIONS[last]]
  return number, ' '.join(rest).lower()


def build_queries():
  selected = read_json(os.path.join(DATA_DIR, 'selected.json'), {}) or {}
  engine = read_json(os.path.join(DATA_DIR, 'engine_results.json'), {}) or {}
  queries = []
  for jurisdiction, candidate in selected.items():
    result = engine.get(jurisdiction) or {}
    resolved = result.get('resolved') or {}
    # Prefer what the pipeline actually resolved (its situs and coordinate are
    # the parcel the engine labeled); fall back to the selection record.
    situs = resolved.get('situs') or candidate['address']
    # The coordinate is what actually resolves the property on their side
    # (verified: address parts alone 404, a coordinate alone succeeds), so it
    # has to be a point INSIDE the parcel — an L-shaped lot's centroid can fall
    # in the street, and a point in the right-of-way returns 404.
    lat, lng = resolved.get('lat', candidate['lat']), resolved.get('lng', candidate['lng'])
    if resolved.get('boundary'):
      try:
        point = shapely_wkt.loads(resolved['boundary']).representative_point()
        lat, lng = point.y, point.x
      except Exception:
        pass
    city = resolved.get('city_name') or candidate.get('situs_city') or ''
    if jurisdiction.endswith('(unincorporated)'):
      city = candidate.get('situs_city') or city
    number, street = split_situs(situs)
    queries.append({
      'jurisdiction': jurisdiction,
      'params': {
        'addr_state': 'ca',
        'addr_city': (city or '').lower(),
        'addr_zip': '',
        'addr_street': street,
        'addr_num': number,
        'lat': str(lat),
        'lng': str(lng),
        'property_id': '',
      },
    })
  return queries


PROBE = """
// FutureLot front-edge probe — read-only GETs against the report route the
// page itself calls. Returns one record per QA lot.
(async () => {
  const QUERIES = %s;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const out = [];
  for (const q of QUERIES) {
    const url = '/api/street-data?params=' + encodeURIComponent(JSON.stringify(q.params));
    let rec = { jurisdiction: q.jurisdiction, params: q.params };
    try {
      const res = await fetch(url, { credentials: 'include' });
      rec.status = res.status;
      if (res.ok) {
        const j = await res.json();
        const simplified = j.lot_simplified || {};
        rec.lot = (simplified.lot || j.lot || {}).coordinates || null;
        rec.edges = (simplified.lot_edges || []).map(e => ({
          type: e.edge_type,
          len: Math.round(e.length * 10) / 10,
          v: (e.vertexes || []).map(p => [Math.round(p[0] * 1e6) / 1e6, Math.round(p[1] * 1e6) / 1e6]),
        }));
        const a = j.attributes || {};
        rec.attributes = { address: a.address, zone_code: a.zone_code,
                           lot_size: a.lot_size, property_id: a.property_id,
                           parcel_id: a.parcel_id, county: a.county,
                           zoning_jurisdiction: a.zoning_jurisdiction,
                           canonical_url: a.canonical_url };
        // The detached-ADU column of the sidebar the screenshots show:
        // ext_setbacks is the exterior (detached) ADU, int_setbacks the interior.
        const placement = ((j.bylaws || {}).adu || {}).placement || {};
        const pick = s => s ? { front_val: s.front_val, front: s.front,
                                side_val: s.side_val, side: s.side,
                                rear_val: s.rear_val, rear: s.rear } : null;
        rec.adu_setbacks = { ext: pick(placement.ext_setbacks),
                             int: pick(placement.int_setbacks),
                             status: placement.status };
      } else {
        rec.body = (await res.text()).slice(0, 200);
      }
    } catch (e) {
      rec.error = String(e);
    }
    out.push(rec);
    await sleep(1200);
  }
  return JSON.stringify(out);
})()
"""


if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  # A browser tool call has its own timeout; 28 sequential requests with a
  # courtesy pause can outlast it. Emit the probe in slices and concatenate.
  parser.add_argument('--start', type=int, default=0)
  parser.add_argument('--count', type=int, default=0, help='0 = to the end')
  arguments = parser.parse_args()
  queries = build_queries()
  end = len(queries) if arguments.count <= 0 else arguments.start + arguments.count
  print(PROBE % json.dumps(queries[arguments.start:end], indent=0).replace('\n', ''))
