"""
unpack_probe.py
---------------
Phase C, part 2: turn the browser probe's compact form back into the
observation records compare.py reads.

The browser tool truncates long return values, so the probe hands back a
packed encoding rather than raw JSON: per lot an origin coordinate and each
edge as integer offsets from it in millionths of a degree. That is lossless
here — the parcel fabrics are served at geometryPrecision 6 (~0.1 m), which is
the same grid — and it fits the whole 28-lot payload in a handful of reads.

  python3 qa/front-edge/unpack_probe.py packed.json

Reads the packed array (a file, or stdin) and writes
data/futurelot_observations.json.
"""
import json
import os
import sys

from qa_common import DATA_DIR, write_json

TAGS = {'f': 'front', 'r': 'rear', 's': 'side'}


def unpack(packed):
  records = []
  for row in packed:
    origin_lng, origin_lat = row['o']
    edges = []
    for tag, length, x1, y1, x2, y2 in row['e']:
      edges.append({
        'type': TAGS.get(tag, tag),
        'len': length,
        'v': [[round(origin_lng + x1 / 1e6, 6), round(origin_lat + y1 / 1e6, 6)],
              [round(origin_lng + x2 / 1e6, 6), round(origin_lat + y2 / 1e6, 6)]],
      })
    parcel_id, zone_code, lot_size, property_id, zoning_jurisdiction, county = row['a']
    front, side, rear = row['sb']
    records.append({
      'jurisdiction': row['j'],
      'status': row['s'],
      # The lot ring is the edge chain closed back on itself.
      'lot': [[e['v'][0] for e in edges] + [edges[0]['v'][0]]] if edges else [],
      'edges': edges,
      'attributes': {'parcel_id': parcel_id, 'zone_code': zone_code, 'lot_size': lot_size,
                     'property_id': property_id, 'zoning_jurisdiction': zoning_jurisdiction,
                     'county': county},
      # Detached ("exterior") ADU setbacks — the column the report sidebar shows.
      # FutureLot encodes "not permitted" as a sentinel (1e6 / 2e6), not a distance.
      'adu_setbacks': {'ext': {'front_val': front, 'side_val': side, 'rear_val': rear}},
    })
  return records


def main():
  source = open(sys.argv[1], encoding='utf-8') if len(sys.argv) > 1 else sys.stdin
  packed = json.load(source)
  records = unpack(packed)
  path = os.path.join(DATA_DIR, 'futurelot_observations.json')
  write_json(path, records)
  print('wrote %d observations to %s' % (len(records), path))


if __name__ == '__main__':
  main()
