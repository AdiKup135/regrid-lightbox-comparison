"""
offset.py
---------
The buildable envelope: the lot polygon with each edge's setback strip removed.

Every labeled edge is offset inward by its own distance. Rather than
intersecting offset lines (exact only on convex lots, and fiddly at corners
where a 0 ft edge meets a 4 ft edge), each edge is buffered by its setback and
the strip is subtracted from the lot. Square end caps extend the strip past
the edge's endpoints so adjacent strips overlap at corners instead of leaving
slivers. On a convex lot this is identical to the offset-line construction;
on a concave lot the square caps can bite slightly into the interior at a
reflex corner, so the result is flagged there.

Distances are in feet on the labeler's local tangent plane
(parcel_edges.geometry.make_projection), so the polygon is computed in feet
and projected back to EPSG:4326 for the wire.
"""
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, MultiPolygon, Polygon

from services.compute.parcel_edges.geometry import Pt, make_projection, parse_wkt_outer_ring

from .state_track import EdgeSetback

# A lot whose convex hull exceeds its own area by more than this share has a
# reflex corner the buffer construction only approximates.
_CONCAVITY_TOLERANCE = 0.01
FLAG_CONCAVE_LOT = 'concave_lot_offset_approximation'
# An edge with no value (front setback not in the database) is drawn at 0 ft;
# the envelope is then an upper bound until the value is entered.
FLAG_ENVELOPE_MISSING_VALUE = 'envelope_drawn_without_missing_setback'


def setback_polygon(boundary_wkt: str, edges: Sequence[Dict], setbacks: Sequence[EdgeSetback],
                    origin_lng: float, origin_lat: float) -> Tuple[Optional[str], float, List[str]]:
  """Offset the lot inward, edge by edge.

  @param boundary_wkt The subject parcel boundary, EPSG:4326 WKT.
  @param edges The labeled edges (LotEdge.to_dict()); ``pts`` is [[lng, lat], ...].
  @param setbacks One EdgeSetback per edge, same order.
  @param origin_lng @param origin_lat Projection origin — the subject's point.

  @return (envelope WKT in EPSG:4326, or None if nothing is left; its area in
    sq ft; lot-level flags).
  """
  projection = make_projection(origin_lng, origin_lat)
  ring_ll = parse_wkt_outer_ring(boundary_wkt)
  lot = Polygon([projection.to_ft(p) for p in ring_ll])
  if not lot.is_valid:
    lot = lot.buffer(0)
  flags: List[str] = []
  if lot.convex_hull.area > lot.area * (1 + _CONCAVITY_TOLERANCE):
    flags.append(FLAG_CONCAVE_LOT)

  envelope = lot
  for edge, setback in zip(edges, setbacks):
    if setback.setback_ft is None:
      if FLAG_ENVELOPE_MISSING_VALUE not in flags:
        flags.append(FLAG_ENVELOPE_MISSING_VALUE)
      continue
    if setback.setback_ft <= 0:
      continue
    pts_ft = [projection.to_ft((float(p[0]), float(p[1]))) for p in edge.get('pts') or []]
    if len(pts_ft) < 2:
      continue
    strip = LineString(pts_ft).buffer(setback.setback_ft, cap_style='square', join_style='mitre')
    envelope = envelope.difference(strip)

  if envelope.is_empty:
    flags.append('envelope_empty')
    return None, 0.0, flags
  if isinstance(envelope, MultiPolygon):
    # Setbacks can pinch a lot into pieces; the buildable one is the largest.
    envelope = max(envelope.geoms, key=lambda g: g.area)
    flags.append('envelope_split_largest_kept')

  area_sqft = round(envelope.area, 1)
  ring_ft: List[Pt] = list(envelope.exterior.coords)
  ring_back = [projection.to_ll(p) for p in ring_ft]
  # 9 decimals ≈ 0.3 mm: the WKT round-trips to within a fraction of a sq ft of `area_sqft`.
  wkt = 'POLYGON ((%s))' % ', '.join('%.9f %.9f' % (lng, lat) for lng, lat in ring_back)
  return wkt, area_sqft, flags
