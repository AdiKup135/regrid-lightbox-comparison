"""Decode ONE Zoneomics vector tile and report exactly what is in it.

Open question this settles (costs a single API call):
  1. Which LAYERS does the MVT actually carry? The public documentation lists
     zoning attributes but never enumerates layers, so a parcel layer or a
     right-of-way layer cannot be ruled out from the docs alone.
  2. Do any features carry a street/road NAME or an APN?
  3. If it is zoning-only, do streets appear as explicit features, or as the
     unzoned GAPS between zone polygons? The gaps would still be usable as a
     right-of-way mask — an independent check on which parcel edges face a
     street.

Usage:
    python3 probe_tiles.py                      # uses 1590 Madrono, Palo Alto
    python3 probe_tiles.py <lat> <lng> [zoom]

Requires: pip install mapbox-vector-tile requests
Reads ZONEOMICS_API_KEY from site/.env. Never prints the key.
"""
import json
import math
import sys

import requests

ENV_PATH = "/Users/adi/Documents/formX/site/.env"
TILES_URL = "https://api.zoneomics.com/v2/tiles"
# The documented minimum zoom for this endpoint.
MIN_ZOOM = 15


def read_key() -> str:
  for line in open(ENV_PATH):
    if line.startswith("ZONEOMICS_API_KEY="):
      return line.split("=", 1)[1].strip()
  raise SystemExit("ZONEOMICS_API_KEY not found in %s" % ENV_PATH)


def lat_lng_to_tile(lat: float, lng: float, zoom: int):
  """Web Mercator tile coordinates for a point."""
  n = 2 ** zoom
  x = int((lng + 180.0) / 360.0 * n)
  lat_rad = math.radians(lat)
  y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
  return x, y


def main() -> None:
  lat = float(sys.argv[1]) if len(sys.argv) > 1 else 37.432407733295996
  lng = float(sys.argv[2]) if len(sys.argv) > 2 else -122.15218469089903
  zoom = int(sys.argv[3]) if len(sys.argv) > 3 else MIN_ZOOM
  if zoom < MIN_ZOOM:
    raise SystemExit("zoom must be >= %d for this endpoint" % MIN_ZOOM)

  x, y = lat_lng_to_tile(lat, lng, zoom)
  print("tile z=%d x=%d y=%d for (%.6f, %.6f)" % (zoom, x, y, lat, lng))

  response = requests.get(TILES_URL, params={"x": x, "y": y, "z": zoom, "api_key": read_key()}, timeout=45)
  print("http=%s  content-type=%s  bytes=%d"
        % (response.status_code, response.headers.get("content-type"), len(response.content)))
  if not response.ok:
    # A 429 here means quota, not an empty tile — the distinction that a naive
    # probe misses.
    print("body: %s" % response.text[:300])
    return
  if not response.content:
    print("empty tile body — no features at this location/zoom")
    return

  try:
    import mapbox_vector_tile
  except ImportError:
    raw = "tile.mvt"
    open(raw, "wb").write(response.content)
    print("saved raw tile to %s — install mapbox-vector-tile to decode" % raw)
    return

  decoded = mapbox_vector_tile.decode(response.content)
  print("\nLAYERS: %s" % sorted(decoded.keys()))
  for layer_name, layer in decoded.items():
    features = layer.get("features", [])
    print("\n--- layer %r: %d features" % (layer_name, len(features)))
    keys = sorted({k for f in features for k in (f.get("properties") or {})})
    print("    property keys: %s" % keys)
    geom_types = sorted({(f.get("geometry") or {}).get("type") for f in features})
    print("    geometry types: %s" % geom_types)
    # The three things worth knowing, called out explicitly.
    name_like = [k for k in keys if any(t in k.lower() for t in ("name", "street", "road", "route"))]
    id_like = [k for k in keys if any(t in k.lower() for t in ("apn", "parcel", "pin"))]
    row_like = [k for k in keys if any(t in k.lower() for t in ("row", "right_of_way", "way"))]
    print("    name-like: %s | parcel-id-like: %s | row-like: %s" % (name_like, id_like, row_like))
    for feature in features[:2]:
      print("    sample properties: %s" % json.dumps(feature.get("properties"), default=str)[:300])


if __name__ == "__main__":
  main()
