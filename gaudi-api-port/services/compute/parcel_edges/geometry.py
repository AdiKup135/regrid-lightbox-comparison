"""
geometry.py
-----------
Planar geometry primitives for parcel edge labeling, in feet on a local
tangent plane.

Parcel boundaries arrive as EPSG:4326 WKT. Every measurement in the labeling
pipeline is a distance or an angle in feet, so the boundary is projected once
onto a flat plane centred on the subject parcel and all downstream work is
plain planar geometry.

Shapely owns WKT parsing, point-in-polygon, and point-to-boundary distance
(see Ring). The projection is deliberately a local equirectangular
approximation rather than pyproj/State Plane: over a single parcel and its
immediate neighbours (a few hundred feet) the error is far below the
sub-foot tolerances this module works at, and it keeps the package free of
dependencies gaudi-api does not already carry. See README for the upgrade
path.
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from shapely import from_wkt
from shapely.geometry import LinearRing, Point, Polygon
from shapely.prepared import prep

Pt = Tuple[float, float]

# Feet per degree of latitude. Longitude is scaled by cos(latitude).
FT_PER_DEG_LAT: float = 364567.2


@dataclass(frozen=True)
class Projection:
  """Local tangent plane centred on (origin_lng, origin_lat)."""

  origin_lng: float
  origin_lat: float
  ft_per_deg_lng: float

  def to_ft(self, pt: Pt) -> Pt:
    lng, lat = pt
    return ((lng - self.origin_lng) * self.ft_per_deg_lng,
            (lat - self.origin_lat) * FT_PER_DEG_LAT)

  def to_ll(self, pt: Pt) -> Pt:
    x, y = pt
    return (self.origin_lng + x / self.ft_per_deg_lng,
            self.origin_lat + y / FT_PER_DEG_LAT)


def make_projection(origin_lng: float, origin_lat: float) -> Projection:
  """Build the local tangent plane for a parcel centroid.

  @param origin_lng Centroid longitude (EPSG:4326).
  @param origin_lat Centroid latitude (EPSG:4326).

  @return A Projection converting between [lng, lat] and feet.
  """
  return Projection(origin_lng, origin_lat,
                    FT_PER_DEG_LAT * math.cos(math.radians(origin_lat)))


class Ring:
  """A closed boundary as both an indexable vertex list and Shapely geometry.

  The pipeline indexes and slices vertices (which Shapely does not help with)
  while also asking "is this point inside" and "how far is this point from the
  boundary" thousands of times (which Shapely does far better than a hand
  rolled loop). This holds both views of one ring so they cannot drift.

  Note: ``contains`` uses Shapely's interior test, so a point exactly ON the
  boundary is NOT contained. Every caller probes a point offset from the
  boundary by whole feet, so the distinction never arises in practice.
  """

  __slots__ = ("pts", "polygon", "line", "bounds", "_prepared")

  def __init__(self, pts: Sequence[Pt]):
    self.pts: List[Pt] = [tuple(p) for p in pts]
    self.polygon = Polygon(self.pts)
    self.line = LinearRing(self.pts)
    self.bounds = self.polygon.bounds
    self._prepared = prep(self.polygon)

  def __len__(self) -> int:
    return len(self.pts)

  def contains(self, pt: Pt) -> bool:
    """True when pt lies strictly inside the ring."""
    return self._prepared.contains(Point(pt))

  def distance_to_boundary(self, pt: Pt) -> float:
    """Shortest distance (ft) from pt to the ring's boundary line."""
    return self.line.distance(Point(pt))

  def near(self, pt: Pt, tolerance: float) -> bool:
    """Cheap bounding-box reject used before distance_to_boundary.

    A point outside the ring's bounding box expanded by ``tolerance`` cannot
    be within ``tolerance`` of the boundary, so this only ever skips work — it
    can never change which neighbour a sample is attributed to.
    """
    min_x, min_y, max_x, max_y = self.bounds
    return (min_x - tolerance <= pt[0] <= max_x + tolerance
            and min_y - tolerance <= pt[1] <= max_y + tolerance)


def parse_wkt_outer_ring(wkt: str) -> List[Pt]:
  """WKT MULTIPOLYGON/POLYGON -> outer ring of the largest polygon.

  The closing duplicate vertex is dropped so the ring can be indexed modulo
  its length. Interior rings (holes) are ignored — a parcel's outer boundary
  is the only thing that abuts anything.

  @param wkt WKT geometry string, EPSG:4326, lng-lat order.

  @return Outer ring vertices as [(lng, lat), ...], no closing duplicate.

  @raise ValueError When the WKT cannot be parsed or has fewer than 3 vertices.
  """
  try:
    geom = from_wkt(wkt)
  except Exception as exc:  # shapely raises GEOSException subclasses
    raise ValueError(f"Unparseable WKT boundary: {wkt[:60]}...") from exc
  if geom is None or geom.is_empty:
    raise ValueError(f"Unparseable WKT boundary: {wkt[:60]}...")

  if geom.geom_type == "MultiPolygon":
    polygon = max(geom.geoms, key=lambda g: g.area)
  elif geom.geom_type == "Polygon":
    polygon = geom
  else:
    raise ValueError(f"Boundary is not a polygon: {geom.geom_type}")

  ring = [(float(x), float(y)) for x, y in polygon.exterior.coords]
  if len(ring) > 1 and ring[0] == ring[-1]:
    ring.pop()
  if len(ring) < 3:
    raise ValueError("Boundary ring has fewer than 3 vertices")
  return ring


def dist(a: Pt, b: Pt) -> float:
  """Euclidean distance between two planar points."""
  return math.hypot(a[0] - b[0], a[1] - b[1])


def outward_normal(a: Pt, b: Pt, ring: Ring) -> Pt:
  """Unit normal of segment ab pointing away from the ring's interior.

  Orientation is decided by testing which side is outside, so the result does
  not depend on the ring's winding direction.
  """
  dx, dy = b[0] - a[0], b[1] - a[1]
  length = math.hypot(dx, dy) or 1.0
  nx, ny = dy / length, -dx / length
  mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
  if ring.contains((mid[0] + nx * 2, mid[1] + ny * 2)):
    nx, ny = -nx, -ny
  return (nx, ny)


def dir_deg(a: Pt, b: Pt) -> float:
  """Direction of travel from a to b, in degrees (-180, 180]."""
  return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def ang_diff(x: float, y: float) -> float:
  """Unsigned difference between two headings, in degrees [0, 180]."""
  d = abs(x - y) % 360
  return 360 - d if d > 180 else d


def line_intersect(p1: Pt, d1: Pt, p2: Pt, d2: Pt) -> Optional[Pt]:
  """Intersection of two infinite lines given as point + direction.

  @return The intersection point, or None when the lines are parallel.
  """
  det = d1[0] * d2[1] - d1[1] * d2[0]
  if abs(det) < 1e-9:
    return None
  t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / det
  return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def ring_winding_sign(pts: Sequence[Pt]) -> int:
  """+1 when the ring is counter-clockwise, -1 when clockwise.

  Used to tell a convex lot corner from a concave cul-de-sac bulb: with the
  interior on the left of travel a lot corner turns one way and a bulb wraps
  the other, mirrored for the opposite winding.
  """
  area2 = 0.0
  n = len(pts)
  for i in range(n):
    x1, y1 = pts[i]
    x2, y2 = pts[(i + 1) % n]
    area2 += x1 * y2 - x2 * y1
  return sign(area2) or 1


def sign(x: float) -> int:
  """Sign of x as -1, 0, or 1."""
  return (x > 0) - (x < 0)


def round_half_up(x: float, decimals: int = 1) -> float:
  """Round half away from zero at the given precision.

  Python's built-in round() is banker's rounding, which would report a
  different edge length than the reference implementation for exact halves.
  """
  factor = 10 ** decimals
  return math.floor(x * factor + 0.5) / factor
