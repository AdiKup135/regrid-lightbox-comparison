"""
edge_labeling.py
----------------
Labels each edge of a subject parcel as front / street_side / side / rear.

Approach (identity over geometry):
  1. Attribute the boundary: sample who is across each stretch — a neighbour
     parcel or nothing (nothing = street right-of-way).
  2. Census the surroundings: how many separate road gaps, and which street
     name(s) the neighbours along each gap carry.
  3. Build edges: breaks occur ONLY at street/neighbour transitions, at sharp
     corners inside shared stretches, and at street splits inside a road gap
     (split at the virtual corner / bisector crossing) — census-confirmed by
     two street names, or, when situs addresses are missing and the census is
     blind, a geometric CONVEX turn between long straight sections (a lot
     wrapping a block corner; concave cul-de-sac bulbs never split). A change
     of neighbour along a straight line does NOT break an edge; a curved
     single-street frontage (cul-de-sac) stays ONE edge.
  4. Label in a single pass: the front is decided once, from the first
     evidence source that yields an answer, and never revised.

The per-jurisdiction front-declaration method lives OUTSIDE this module, in
the unified jurisdiction db (front_rule per record, matched by Zoneomics
city_id). The caller looks the rule up and passes it in as ``front_rule``.

This module does not compute setback values — that is the rules engine's job,
downstream of these labels.
"""
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .geometry import (
  Pt,
  Ring,
  ang_diff,
  dir_deg,
  dist,
  line_intersect,
  make_projection,
  outward_normal,
  parse_wkt_outer_ring,
  ring_winding_sign,
  round_half_up,
  sign,
)
from .street_names import extract_street_name, normalize_street_key

# --- Front rules -------------------------------------------------------------
# How a jurisdiction declares which frontage of a multi-street lot is the legal
# front. Sourced from the jurisdiction db — never hardcoded per city here.
FRONT_RULE_SHORTEST_FRONTAGE = "shortest_frontage"
FRONT_RULE_ADDRESS_STREET = "address_street"
FRONT_RULE_DESIGNATED = "designated"
FRONT_RULE_OWNER_ELECTED = "owner_elected"
FRONT_RULE_ALL_FRONTS = "all_fronts"

FRONT_RULES = frozenset({
  FRONT_RULE_SHORTEST_FRONTAGE,
  FRONT_RULE_ADDRESS_STREET,
  FRONT_RULE_DESIGNATED,
  FRONT_RULE_OWNER_ELECTED,
  FRONT_RULE_ALL_FRONTS,
})

# The engine's silent default when a jurisdiction carries no record: the street
# named in the situs address is the front.
DEFAULT_FRONT_RULE = FRONT_RULE_ADDRESS_STREET

# Marker owner for an unowned stretch that probing proved to be a parcel-fabric
# sliver rather than a street.
_HOLE = "__attribution_gap__"


@dataclass
class ZoneomicsParcel:
  """One parcel, exactly as it appears in zoneDetail -> data.parcels[]."""

  apn: str
  # Situs address, e.g. "804 Lennox Ct Sunnyvale CA" — street names feed the
  # census that identifies which street each road gap belongs to.
  address: str
  # Parcel centroid.
  lat: float
  lng: float
  # WKT MULTIPOLYGON, EPSG:4326 (lng lat order).
  boundary: str


@dataclass
class FrontRuleOverride:
  """A conditional exception to the base front rule.

  Mirrors ``front_rule.overrides`` in the jurisdiction db, field for field, so
  db records can be passed in verbatim. Overrides are evaluated in order and
  the first whose condition holds replaces the base rule. A condition this
  engine cannot evaluate (missing zone info, unknown condition kind) is
  skipped; if no other override applies, the base rule yields to the
  address-street default, because an override might have applied and the base
  rule is therefore in doubt. The 'front_rule_override_unevaluated' lot flag
  records that for logs and debugging.
  """

  rule: str
  # 'oversized_corner_lot' — every street frontage exceeds the zone-type
  #   threshold (e.g. SJMC 20.200.670(A): 120 ft residential / 150 ft
  #   commercial, BOTH frontages must exceed). Frontage is summed per street
  #   name; unnamed street edges count individually.
  # 'pedestrian_oriented_district' — the subject's zone_code is one of
  #   zone_codes (e.g. SJMC 20.200.670(B): MS-G, MS-C).
  condition: str = ""
  citation: Optional[str] = None
  description: Optional[str] = None
  # oversized_corner_lot only: per-zone-type frontage thresholds (ft).
  thresholds_ft: Optional[Dict[str, float]] = None
  # pedestrian_oriented_district only: zone codes the condition matches.
  zone_codes: Optional[List[str]] = None

  @classmethod
  def from_db(cls, record: Dict) -> "FrontRuleOverride":
    """Build an override from a raw jurisdiction-db dict, ignoring extras."""
    return cls(
      rule=record.get("rule", ""),
      condition=record.get("condition", ""),
      citation=record.get("citation"),
      description=record.get("description"),
      thresholds_ft=record.get("thresholds_ft"),
      zone_codes=record.get("zone_codes"),
    )


@dataclass(frozen=True)
class EdgeLabelingConfig:
  """Geometric tolerances. Every value is in feet or degrees."""

  # Max distance between the subject boundary and a neighbour boundary to
  # consider them the same line. Parcel fabrics have small slivers.
  snap_tolerance_ft: float = 1.0
  # Sampling step used only to MEASURE who is across the boundary. Sampling
  # never creates edge breaks.
  attribution_step_ft: float = 5.0
  # Consecutive boundary vertices closer than this are merged at parse time —
  # real parcel fabrics carry survey-noise micro-vertices.
  vertex_dedupe_ft: float = 0.5
  # Corner test: direction is measured over this much boundary on EACH side of
  # a vertex (never between adjacent samples, which is noise).
  arm_length_ft: float = 10.0
  # Corner band: the arm directions must differ by at least corner_min_deg AND
  # less than corner_max_deg to split. Below min = straight/curved line; at or
  # above max = the boundary doubles back (spike/sliver artifact) — no split,
  # flagged 'boundary_spike'. Sustained gentle curvature (a cul-de-sac arc)
  # never reaches the band.
  corner_min_deg: float = 45.0
  corner_max_deg: float = 170.0
  # Unowned stretch triage: probe this far outward from the boundary. Probe
  # points landing INSIDE a neighbour polygon mean the "gap" is a parcel-fabric
  # sliver (absorbed into the shared edge, flagged 'attribution_gap'); open
  # space means real right-of-way — a street — regardless of stretch length.
  gap_probe_ft: float = 8.0
  # Rear tie-break: candidates within this of the best anti-parallel score are
  # tied; the longest tied candidate wins.
  rear_tie_epsilon: float = 0.1
  # Road-gap corner fallback: when the street-name census cannot resolve two
  # names, a gap still splits at a CONVEX turn of at least this many degrees
  # between long straight sections (a lot wrapping a rounded block corner).
  # Concave turns — cul-de-sac bulbs — never split, and a turn whose flanking
  # sections carry the SAME census name (a street bend) never splits.
  road_gap_corner_min_deg: float = 60.0
  # A straight section of a road gap must be at least this long to take part in
  # the street-name census.
  min_wing_ft: float = 25.0
  # Lateral distance (ft) and direction slack (deg) for deciding that a
  # neighbour's boundary lies along the same street line as a frontage section.
  block_face_lateral_ft: float = 12.0
  block_face_angle_deg: float = 15.0
  # An edge qualifies as rear only if its outward normal is at least this
  # anti-parallel to the front's (dot <= -threshold). Triangular lots
  # legitimately have no rear.
  rear_dot_threshold: float = 0.3


DEFAULT_CONFIG = EdgeLabelingConfig()


@dataclass
class EdgeLabelingInput:
  subject: ZoneomicsParcel
  # All parcels from the radius pull except the subject (same-APN entries are
  # skipped defensively).
  neighbors: List[ZoneomicsParcel] = field(default_factory=list)
  # From the jurisdiction db (front_rule.rule), matched by city_id.
  front_rule: Optional[str] = None
  # From the jurisdiction db (front_rule.overrides), matched by city_id.
  front_rule_overrides: Optional[List[FrontRuleOverride]] = None
  # Subject zone, exactly as it appears in zoneDetail -> data.zone_details.
  # Feeds override conditions only; absent zone info never changes the base
  # rule, it only leaves overrides unevaluated (flagged).
  zone: Optional[Dict[str, Optional[str]]] = None
  # Owner's election of the front edge (index into the returned edges). Only
  # meaningful where front_rule is 'owner_elected'.
  user_front_override_edge_index: Optional[int] = None
  # The subject's street name from an authoritative source — the Google Places
  # `route` component, which the project record already stores. Preferred over
  # parsing the Zoneomics situs address, which cannot always separate a unit
  # suffix from the street name. Normalized here, so pass the raw route.
  subject_street_name: Optional[str] = None
  # Optional street-naming source (see street_naming.make_google_roads_namer).
  # Called ONCE per lookup with every frontage-section midpoint as (lng, lat),
  # and must return one optional RoadName per point, in order. Where it names a
  # section, that name wins over the neighbour-address census; where it returns
  # None, the census still decides. Absent, the engine behaves exactly as it
  # does with the census alone.
  street_namer: Optional[Callable[[Sequence[Pt]], List[object]]] = None
  config: Optional[EdgeLabelingConfig] = None


@dataclass
class EdgeAbuts:
  """What lies across an edge: a street, or one or more neighbour parcels."""

  kind: str  # 'street' | 'parcels'
  street_name: Optional[str] = None
  # 'roads' (Google Roads API) | 'census' (neighbour situs addresses) | None.
  street_name_source: Optional[str] = None
  apns: List[str] = field(default_factory=list)

  def to_dict(self) -> Dict:
    if self.kind == "street":
      out = {"kind": "street"}
      if self.street_name is not None:
        out["streetName"] = self.street_name
      if self.street_name_source is not None:
        out["streetNameSource"] = self.street_name_source
      return out
    return {"kind": "parcels", "apns": list(self.apns)}


@dataclass
class LotEdge:
  # Ordered vertices of this edge, [lng, lat].
  pts: List[Pt]
  # front = the primary street frontage · street_side = street-facing but not
  # the front (corner lots) · side = shared with neighbour(s) · rear = the edge
  # most opposite the front.
  tag: str
  abuts: EdgeAbuts
  length_ft: float
  # How the tag was decided: single_frontage | address_match |
  # jurisdiction_rule | geometry | user_override.
  basis: str
  confidence: str  # high | medium | low
  # e.g. 'owner_electable', 'through_lot', 'second_front' (this street_side
  # edge is legally a front too — all_fronts jurisdictions; the primary front
  # keeps the 'front' tag because the two often carry different setbacks).
  flags: List[str] = field(default_factory=list)

  def to_dict(self) -> Dict:
    """Serialize to the wire shape the existing consumers already read."""
    return {
      "pts": [list(p) for p in self.pts],
      "tag": self.tag,
      "abuts": self.abuts.to_dict(),
      "lengthFt": self.length_ft,
      "basis": self.basis,
      "confidence": self.confidence,
      "flags": list(self.flags),
    }


@dataclass
class EdgeLabelingStats:
  road_gaps: int
  street_names: List[str]
  neighbors_touching: int

  def to_dict(self) -> Dict:
    return {
      "roadGaps": self.road_gaps,
      "streetNames": list(self.street_names),
      "neighborsTouching": self.neighbors_touching,
    }


@dataclass
class EdgeLabelingResult:
  edges: List[LotEdge]
  # Lot-level flags: 'no_street_frontage', 'front_requires_review',
  # 'second_front_jurisdiction', 'through_lot', 'unknown_street_name',
  # 'front_rule_override_applied', 'front_rule_override_unevaluated',
  # 'attribution_gap', 'boundary_spike', 'street_namer_failed'.
  flags: List[str]
  stats: EdgeLabelingStats

  def to_dict(self) -> Dict:
    return {
      "edges": [e.to_dict() for e in self.edges],
      "flags": list(self.flags),
      "stats": self.stats.to_dict(),
    }


# --- Internal pipeline types --------------------------------------------------

@dataclass
class _Sample:
  pt: Pt
  is_vertex: bool
  owner: Optional[str] = None


@dataclass(eq=False)
class _Section:
  """A straight piece of a road gap. Indices are positions within the gap.

  eq=False keeps identity semantics: sections are used as dict keys and must
  compare as distinct objects even when their numbers coincide.
  """

  start: int
  end: int
  dir: float
  length_ft: float


@dataclass
class _Gap:
  idx: List[int]
  sections: List[_Section]
  names: Dict[str, List[_Section]]
  # street name -> 'roads' | 'census', whichever source supplied it.
  name_sources: Dict[str, str] = field(default_factory=dict)


@dataclass(eq=False)
class _RawEdge:
  """eq=False so edges are keyed by identity while being collected."""

  sample_idx: List[int]
  street: bool
  apns: List[str]
  street_name: Optional[str]
  length_ft: float
  normal: Pt
  # 'roads' | 'census' | None — provenance of street_name, for debugging.
  street_name_source: Optional[str] = None


@dataclass
class _Neighbor:
  apn: str
  address: str
  ring: Ring


class _Stretch:
  """A contiguous run of samples sharing one owner (or none)."""

  __slots__ = ("owner", "idx")

  def __init__(self, owner: Optional[str], idx: List[int]):
    self.owner = owner
    self.idx = idx


def label_edges(data: EdgeLabelingInput) -> EdgeLabelingResult:
  """Label every edge of the subject parcel.

  @param data Subject parcel, neighbours, and the jurisdiction's front rule.

  @return Labeled edges, lot-level flags, and census statistics.

  @raise ValueError When the subject boundary cannot be parsed.
  """
  cfg = data.config or DEFAULT_CONFIG
  # Silent-code default: the addressed street is the front. Overrides may
  # replace it below.
  front_rule = data.front_rule or DEFAULT_FRONT_RULE
  global_flags: List[str] = []

  def flag(name: str) -> None:
    if name not in global_flags:
      global_flags.append(name)

  # --- 1. Parse, project, sample ---------------------------------------------
  # The boundary is resampled at attribution_step_ft purely to measure who is
  # across each stretch; original vertices are kept and marked, because only
  # vertices can become corners.
  proj = make_projection(data.subject.lng, data.subject.lat)
  ring_ll = parse_wkt_outer_ring(data.subject.boundary)
  ring_pts = [proj.to_ft(p) for p in ring_ll]

  # Merge survey-noise micro-vertices (including the ring wrap).
  deduped: List[Pt] = []
  for i, pt in enumerate(ring_pts):
    if i == 0 or dist(pt, ring_pts[i - 1]) >= cfg.vertex_dedupe_ft:
      deduped.append(pt)
  if len(deduped) > 3 and dist(deduped[0], deduped[-1]) < cfg.vertex_dedupe_ft:
    deduped.pop()
  ring = Ring(deduped)

  samples: List[_Sample] = []
  for i in range(len(ring)):
    a = ring.pts[i]
    b = ring.pts[(i + 1) % len(ring)]
    samples.append(_Sample(a, True))
    n_extra = int(dist(a, b) // cfg.attribution_step_ft)
    for k in range(1, n_extra + 1):
      t = k / (n_extra + 1)
      samples.append(_Sample((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), False))
  n_samples = len(samples)

  def at(i: int) -> _Sample:
    return samples[i % n_samples]

  neighbors: List[_Neighbor] = []
  for parcel in data.neighbors:
    if parcel.apn == data.subject.apn:
      continue
    try:
      pts = [proj.to_ft(p) for p in parse_wkt_outer_ring(parcel.boundary)]
      neighbors.append(_Neighbor(parcel.apn, parcel.address, Ring(pts)))
    except Exception:
      # An unparseable neighbour boundary drops that neighbour, never the lookup.
      continue

  # --- 2. Attribution: who is across each sample -----------------------------
  # A sample belongs to a neighbour when it lies within snap_tolerance_ft of
  # that neighbour's boundary. Ownership changes never create edge breaks.
  for sample in samples:
    for neighbor in neighbors:
      if not neighbor.ring.near(sample.pt, cfg.snap_tolerance_ft):
        continue
      if neighbor.ring.distance_to_boundary(sample.pt) <= cfg.snap_tolerance_ft:
        sample.owner = neighbor.apn
        break

  # --- 3. Census: road gaps and their street names ---------------------------
  # A road gap = a maximal contiguous stretch of unowned samples. Each gap is
  # decomposed into straight sections; each long-enough section gets a street
  # name by matching neighbours whose boundaries run along the same street line
  # and reading their address street names.
  rot = -1
  for i in range(n_samples):
    if at(i).owner != at(i - 1).owner and (at(i).owner is None or at(i - 1).owner is None):
      rot = i
      break
  if rot < 0:
    for i in range(n_samples):
      if at(i).owner != at(i - 1).owner:
        rot = i
        break
  if rot < 0:
    rot = 0
  order = [(rot + k) % n_samples for k in range(n_samples)]

  stretches: List[_Stretch] = []
  for i in order:
    if stretches and stretches[-1].owner == samples[i].owner:
      stretches[-1].idx.append(i)
    else:
      stretches.append(_Stretch(samples[i].owner, [i]))
  if len(stretches) > 1 and stretches[0].owner == stretches[-1].owner:
    stretches[0].idx = stretches[-1].idx + stretches[0].idx
    stretches.pop()

  # Triage unowned stretches: probe outward from the boundary; probe points
  # inside a neighbour polygon mean the stretch is a parcel-fabric sliver, not
  # a street — reassign it to the shared chain (flag 'attribution_gap'). Open
  # space beyond = real right-of-way, regardless of stretch length.
  for stretch in stretches:
    if stretch.owner is not None or len(stretch.idx) < 1:
      continue
    stations = [stretch.idx[min(len(stretch.idx) - 1, int(t * len(stretch.idx)))]
                for t in (0.25, 0.5, 0.75)]
    inside_votes = 0
    for si in stations:
      a = samples[si].pt
      b = at(si + 1).pt
      nx, ny = outward_normal(a, b, ring)
      hit = False
      for probe in (cfg.gap_probe_ft / 2, cfg.gap_probe_ft):
        q = (a[0] + nx * probe, a[1] + ny * probe)
        if any(nb.ring.contains(q) for nb in neighbors):
          hit = True
          break
      if hit:
        inside_votes += 1
    if inside_votes == len(stations):
      stretch.owner = _HOLE
      for i in stretch.idx:
        samples[i].owner = _HOLE
      flag("attribution_gap")

  # Adjacent edges must share one vertex so the edges tile the full boundary:
  # each road gap is extended on both ends to the adjacent shared sample (the
  # corner pin where lot, neighbour, and street meet).
  def succ(k: int) -> int:
    return stretches[(k + 1) % len(stretches)].idx[0]

  def pred(k: int) -> int:
    return stretches[(k - 1) % len(stretches)].idx[-1]

  def straight_sections(idx: Sequence[int]) -> List[_Section]:
    """Cut a gap where the local direction drifts from the section's start."""
    out: List[_Section] = []
    if len(idx) < 2:
      return out

    def close(start: int, end: int) -> None:
      if end - start < 1:
        return
      length = 0.0
      for m in range(start + 1, end + 1):
        length += dist(samples[idx[m - 1]].pt, samples[idx[m]].pt)
      out.append(_Section(start, end,
                          dir_deg(samples[idx[start]].pt, samples[idx[end]].pt),
                          length))

    s0 = 0
    d0 = dir_deg(samples[idx[0]].pt, samples[idx[1]].pt)
    for k in range(2, len(idx)):
      d = dir_deg(samples[idx[k - 1]].pt, samples[idx[k]].pt)
      if ang_diff(d, d0) > cfg.corner_min_deg / 2:
        close(s0, k - 1)
        s0 = k - 1
        d0 = d
    close(s0, len(idx) - 1)
    return out

  def section_street_name(idx: Sequence[int], sec: _Section) -> Optional[str]:
    """Name a frontage section from the addresses of its block-face neighbours."""
    p0 = samples[idx[sec.start]].pt
    pe = samples[idx[sec.end]].pt
    dlen = dist(p0, pe) or 1.0
    d = ((pe[0] - p0[0]) / dlen, (pe[1] - p0[1]) / dlen)
    # Inward = toward the subject's interior. A block-face continuation lies on
    # the SAME side of the street line as the subject; a parcel across the
    # street (whose own address names a different street at a corner) fails the
    # inward probe and must not vote.
    ox, oy = outward_normal(p0, pe, ring)
    angle_cos = math.cos(math.radians(cfg.block_face_angle_deg))
    counts: Dict[str, int] = {}
    for neighbor in neighbors:
      faces = False
      pts = neighbor.ring.pts
      for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        seg_len = dist(a, b)
        if seg_len < 10:
          continue
        dir_dot = abs(((b[0] - a[0]) / seg_len) * d[0] + ((b[1] - a[1]) / seg_len) * d[1])
        lat_a = abs((a[0] - p0[0]) * -d[1] + (a[1] - p0[1]) * d[0])
        lat_b = abs((b[0] - p0[0]) * -d[1] + (b[1] - p0[1]) * d[0])
        # Curvature tolerance: the near end must sit on the street line; the far
        # end may drift as the street curves away from the section's straight
        # extension (up to 3x the lateral band at 15 degrees).
        laterally_ok = (min(lat_a, lat_b) <= cfg.block_face_lateral_ft
                        and max(lat_a, lat_b) <= 3 * cfg.block_face_lateral_ft)
        if dir_dot <= angle_cos or not laterally_ok:
          continue
        # Same-side probe: step inward from the segment midpoint; a same-side
        # continuation contains that point, an across-the-street parcel does not.
        q = ((a[0] + b[0]) / 2 - ox * cfg.block_face_lateral_ft,
             (a[1] + b[1]) / 2 - oy * cfg.block_face_lateral_ft)
        if neighbor.ring.contains(q):
          faces = True
          break
      if not faces:
        continue
      name = extract_street_name(neighbor.address)
      if name:
        counts[name] = counts.get(name, 0) + 1

    best: Optional[str] = None
    best_count = 0
    for name, count in counts.items():
      if count > best_count:
        best, best_count = name, count
    return best

  gaps: List[_Gap] = []
  for k, stretch in enumerate(stretches):
    if stretch.owner is not None:
      continue
    idx = ([pred(k)] + stretch.idx + [succ(k)]) if len(stretches) > 1 else list(stretch.idx)
    gaps.append(_Gap(idx, straight_sections(idx), {}))

  # Name each gap's long-enough sections. Two evidence sources, best first:
  #   roads  — the injected street_namer (Google Roads API): names the road that
  #            actually runs along the section. One batched call for ALL
  #            sections of ALL gaps.
  #   census — neighbours' situs addresses along the same block face.
  # The namer is authoritative where it answers; the census fills its silences,
  # so the engine still works offline / with no API key. Missing situs
  # addresses stop mattering wherever the namer answers.
  namable: List[Tuple[_Gap, _Section]] = []
  for gap in gaps:
    for sec in gap.sections:
      if sec.length_ft >= cfg.min_wing_ft:
        namable.append((gap, sec))

  road_names: List[Optional[object]] = [None] * len(namable)
  if data.street_namer is not None and namable:
    midpoints: List[Pt] = []
    for gap, sec in namable:
      mid_k = (sec.start + sec.end) // 2
      midpoints.append(proj.to_ll(samples[gap.idx[mid_k]].pt))
    try:
      road_names = list(data.street_namer(midpoints))
    except Exception:
      # A namer failure degrades to census-only labeling, never a failed lookup.
      road_names = [None] * len(namable)
      flag("street_namer_failed")
    if len(road_names) != len(namable):
      road_names = [None] * len(namable)
      flag("street_namer_failed")

  for (gap, sec), road in zip(namable, road_names):
    key = getattr(road, "key", None)
    if key:
      gap.names.setdefault(key, []).append(sec)
      gap.name_sources[key] = "roads"
      continue
    name = section_street_name(gap.idx, sec)
    if name:
      gap.names.setdefault(name, []).append(sec)
      gap.name_sources.setdefault(name, "census")

  # --- 4. Build edges --------------------------------------------------------
  # Street edges: one per road gap — unless the census found two street names in
  # one gap (corner lot with a rounded corner): then split once, at the boundary
  # point nearest the virtual corner (intersection of the two frontage lines;
  # for a fillet this is where the angle bisector crosses).
  # Shared edges: one per contiguous shared chain, split only at sharp corners;
  # each edge lists every neighbour along it.
  raw_edges: List[_RawEdge] = []

  def finish_edge(idxs: Sequence[int], street: bool, street_name: Optional[str],
                  street_name_source: Optional[str] = None) -> None:
    if len(idxs) < 2:
      return
    length = 0.0
    nx_sum = 0.0
    ny_sum = 0.0
    for k in range(1, len(idxs)):
      a = samples[idxs[k - 1]].pt
      b = samples[idxs[k]].pt
      seg = dist(a, b)
      ox, oy = outward_normal(a, b, ring)
      length += seg
      nx_sum += ox * seg
      ny_sum += oy * seg

    apns: List[str] = []
    if not street:
      # A corner vertex sits within tolerance of two neighbours at once; an
      # owner must cover at least two samples of this edge to be listed.
      counts: Dict[str, int] = {}
      for i in idxs:
        owner = samples[i].owner
        if owner and owner != _HOLE:
          counts[owner] = counts.get(owner, 0) + 1
      max_count = max(counts.values()) if counts else 0
      for owner, count in counts.items():
        if count >= 2 or count == max_count:
          apns.append(owner)

    norm = math.hypot(nx_sum, ny_sum) or 1.0
    raw_edges.append(_RawEdge(list(idxs), street, apns, street_name, length,
                              (nx_sum / norm, ny_sum / norm), street_name_source))

  # Shared chains: contiguous shared stretches (possibly several owners), split
  # only at sharp corners at original vertices.
  chains: List[List[int]] = []
  current: List[int] = []
  for stretch in stretches:
    if stretch.owner is None:
      if current:
        chains.append(current)
        current = []
    else:
      current.extend(stretch.idx)  # includes absorbed attribution gaps
  if current:
    chains.append(current)
  # Landlocked lot (no gaps): the single chain is the whole ring — close it.
  if len(chains) == 1 and all(s.owner is not None for s in stretches):
    chains[0].append(chains[0][0])
  # Ring wrap with no gap between the last and first stretches: one chain.
  if len(chains) > 1 and stretches[0].owner is not None and stretches[-1].owner is not None:
    chains[0] = chains[-1] + chains[0]
    chains.pop()

  def arm_turn(chain: Sequence[int], k: int) -> Optional[float]:
    """Direction change across a vertex, measured over arm_length_ft each side.

    Measuring over an arm rather than between adjacent samples is what keeps
    densely digitized fabrics from reading as a string of corners.
    """
    length = 0.0
    i = k
    while i > 0 and length < cfg.arm_length_ft:
      i -= 1
      length += dist(samples[chain[i]].pt, samples[chain[i + 1]].pt)
    if length < cfg.arm_length_ft * 0.6:
      return None
    d_in = dir_deg(samples[chain[i]].pt, samples[chain[k]].pt)

    length = 0.0
    j = k
    while j < len(chain) - 1 and length < cfg.arm_length_ft:
      j += 1
      length += dist(samples[chain[j - 1]].pt, samples[chain[j]].pt)
    if length < cfg.arm_length_ft * 0.6:
      return None
    return ang_diff(d_in, dir_deg(samples[chain[k]].pt, samples[chain[j]].pt))

  for chain in chains:
    s0 = 0
    for k in range(1, len(chain) - 1):
      if not samples[chain[k]].is_vertex:
        continue
      turn = arm_turn(chain, k)
      if turn is None:
        continue
      if cfg.corner_min_deg <= turn < cfg.corner_max_deg:
        finish_edge(chain[s0:k + 1], False, None)
        s0 = k
      elif turn >= cfg.corner_max_deg:
        flag("boundary_spike")
    finish_edge(chain[s0:], False, None)

  # Ring winding sign: with the interior on the left of travel (CCW, +1) a lot
  # corner turns left (+) and a cul-de-sac bulb wraps right (-); mirrored for CW
  # rings. This is what lets the geometric fallback split block corners without
  # ever splitting bulbs.
  ring_sign = ring_winding_sign(ring.pts)

  for gap in gaps:
    idx = gap.idx
    named = list(gap.names.keys())

    def split_point(sec_a: _Section, sec_b: _Section, idx=idx) -> int:
      """Boundary sample nearest the virtual corner of two frontage lines."""
      d_a = (math.cos(math.radians(sec_a.dir)), math.sin(math.radians(sec_a.dir)))
      d_b = (math.cos(math.radians(sec_b.dir)), math.sin(math.radians(sec_b.dir)))
      vc = line_intersect(samples[idx[sec_a.start]].pt, d_a,
                          samples[idx[sec_b.start]].pt, d_b)
      split_at = (sec_a.end + sec_b.start) // 2
      if vc is not None:
        best_d = math.inf
        for k in range(sec_a.end, sec_b.start + 1):
          d = dist(samples[idx[k]].pt, vc)
          if d < best_d:
            best_d = d
            split_at = k
      return split_at

    if len(named) >= 2:
      sec_a = gap.names[named[0]][0]
      secs_b = gap.names[named[-1]]
      split_at = split_point(sec_a, secs_b[-1])
      finish_edge(idx[:split_at + 1], True, named[0], gap.name_sources.get(named[0]))
      finish_edge(idx[split_at:], True, named[-1], gap.name_sources.get(named[-1]))
      continue

    # Census resolved fewer than two names (situs addresses are missing in some
    # county fabrics). Geometric fallback: split at convex turns of at least
    # road_gap_corner_min_deg between long straight sections. A turn whose
    # flanking sections both carry the (single) census name is a street bend,
    # not a corner — never split it.
    sec_name: Dict[int, str] = {}
    for name, secs in gap.names.items():
      for sec in secs:
        sec_name[id(sec)] = name
    longs = [s for s in gap.sections if s.length_ft >= cfg.min_wing_ft]
    cuts: List[int] = []
    for k in range(1, len(longs)):
      a, b = longs[k - 1], longs[k]
      delta = ((b.dir - a.dir + 540) % 360) - 180
      name_a = sec_name.get(id(a))
      same_street = name_a is not None and name_a == sec_name.get(id(b))
      if (abs(delta) >= cfg.road_gap_corner_min_deg
          and sign(delta) == ring_sign and not same_street):
        cuts.append(split_point(a, b))

    def name_of(from_i: int, to_i: int) -> Optional[str]:
      """Name a piece by the census name with the most section length inside."""
      best: Optional[str] = None
      best_len = 0.0
      for name, secs in gap.names.items():
        length = sum(s.length_ft for s in secs if s.start >= from_i and s.end <= to_i)
        if length > best_len:
          best_len = length
          best = name
      return best

    prev = 0
    any_unnamed = False
    for cut in cuts + [len(idx) - 1]:
      if cut <= prev:
        continue
      name = name_of(prev, cut)
      finish_edge(idx[prev:cut + 1], True, name, gap.name_sources.get(name) if name else None)
      if not name:
        any_unnamed = True
      prev = cut
    if any_unnamed:
      flag("unknown_street_name")

  # --- 5. Label — single pass ------------------------------------------------
  # All evidence is now available: the edges, each street edge's name, the
  # subject's own street name, the jurisdiction rule, and any user election. The
  # front is decided once and never revised. The jurisdiction rule is the
  # dispatcher: it selects HOW the front is determined (state law never
  # overrides front designation — it only softens front-setback consequences
  # downstream, in the rules engine).
  street_edges = [e for e in raw_edges if e.street]
  shared_edges = [e for e in raw_edges if not e.street]
  # The subject's street: the Google Places route (already on the project
  # record) is authoritative when provided — it separates unit-suffixed house
  # numbers ("1234-B") from the street where a situs-address parse cannot.
  subject_street = (normalize_street_key(data.subject_street_name)
                    or extract_street_name(data.subject.address))
  addressed = [e for e in street_edges if e.street_name == subject_street] if subject_street else []
  addr_match = addressed[0] if len(addressed) == 1 else None
  shortest = min(street_edges, key=lambda e: e.length_ft) if street_edges else None

  # Jurisdiction conditional overrides. Only relevant on multi-frontage lots — a
  # single frontage is the front under any rule. The first override whose
  # condition holds wins and replaces the base rule.
  if len(street_edges) > 1:
    applied = False
    unresolved = False
    for override in (data.front_rule_overrides or []):
      applies: Optional[bool] = None  # None = condition not evaluable here
      if override.condition == "oversized_corner_lot" and override.thresholds_ft:
        zone_type = (data.zone or {}).get("zone_type")
        zone_type = zone_type.lower() if zone_type else None
        threshold = override.thresholds_ft.get(zone_type) if zone_type in ("residential", "commercial") else None
        if threshold is not None:
          # Frontage per STREET, not per edge: a frontage split into several
          # edges (corner clip, mid-edge break) is one street's frontage.
          by_street: Dict[str, float] = {}
          for i, e in enumerate(street_edges):
            key = e.street_name or f"__unnamed_{i}"
            by_street[key] = by_street.get(key, 0.0) + e.length_ft
          # "BOTH street frontages exceed" generalized: every frontage must.
          applies = len(by_street) > 1 and all(ft > threshold for ft in by_street.values())
      elif override.condition == "pedestrian_oriented_district" and override.zone_codes:
        zone_code = (data.zone or {}).get("zone_code")
        if zone_code:
          zone_code = zone_code.upper()
          applies = any(c.upper() == zone_code for c in override.zone_codes)

      if applies is None:
        flag("front_rule_override_unevaluated")
        unresolved = True
        continue
      if applies:
        front_rule = override.rule
        flag("front_rule_override_applied")
        applied = True
        break
    # An unevaluable condition puts the base rule itself in doubt — the override
    # might have applied. Fall back to the engine's address-street default; the
    # flag above records why, for logs and debugging only.
    if unresolved and not applied:
      front_rule = FRONT_RULE_ADDRESS_STREET

  front: Optional[_RawEdge] = None
  basis = "geometry"
  confidence = "low"

  if len(street_edges) == 1:
    # One frontage — front regardless of rule (covers mid-block and cul-de-sac).
    front = street_edges[0]
    basis, confidence = "single_frontage", "high"
  elif len(street_edges) > 1:
    if front_rule == FRONT_RULE_SHORTEST_FRONTAGE:
      front = shortest
      basis = "jurisdiction_rule"
      confidence = "medium" if (addr_match and addr_match is not shortest) else "high"
    elif front_rule == FRONT_RULE_ADDRESS_STREET:
      if addr_match:
        front, basis, confidence = addr_match, "address_match", "high"
      else:
        front, basis, confidence = shortest, "geometry", "low"
        flag("front_requires_review")
    elif front_rule == FRONT_RULE_OWNER_ELECTED:
      # The owner's election is the rule; until made, default to the addressed
      # street (else shortest).
      elected = None
      i = data.user_front_override_edge_index
      if i is not None and 0 <= i < len(raw_edges) and raw_edges[i].street:
        elected = raw_edges[i]
      if elected is not None:
        front, basis, confidence = elected, "user_override", "high"
      elif addr_match:
        front, basis, confidence = addr_match, "address_match", "medium"
      else:
        front, basis, confidence = shortest, "geometry", "low"
    elif front_rule == FRONT_RULE_DESIGNATED:
      # Designated by an authority or a physical test — not computable.
      front = addr_match or shortest
      basis = "address_match" if addr_match else "geometry"
      confidence = "low"
      flag("front_requires_review")
    elif front_rule == FRONT_RULE_ALL_FRONTS:
      # Every frontage is legally front-type; one is still tagged front so
      # rear/side orientation works. The rules engine maps street_side back.
      front = addr_match or shortest
      basis = "address_match" if addr_match else "geometry"
      confidence = "medium"
      flag("second_front_jurisdiction")
  elif raw_edges:
    # No street frontage: landlocked or flag lot. Guess the shortest edge as the
    # access point; the whole lot is flagged for review.
    flag("no_street_frontage")
    front = min(raw_edges, key=lambda e: e.length_ft)
    basis, confidence = "geometry", "low"

  electable = front_rule == FRONT_RULE_OWNER_ELECTED and len(street_edges) > 1
  tags: Dict[int, Tuple[str, str, str, List[str]]] = {}

  if front is not None:
    tags[id(front)] = ("front", basis, confidence, ["owner_electable"] if electable else [])
  for e in street_edges:
    if e is front:
      continue
    dot = (e.normal[0] * front.normal[0] + e.normal[1] * front.normal[1]) if front else 0.0
    if dot < -0.5:
      extra = ["owner_electable"] if electable else []
      tags[id(e)] = ("rear", "geometry", "medium", ["through_lot"] + extra)
      flag("through_lot")
    else:
      # Under all_fronts every street frontage is legally a front; the tag stays
      # street_side (one anchor front keeps rear/side orientation and the
      # primary/secondary distinction, which carries different setbacks), but
      # the edge itself now says so.
      second = ["second_front"] if front_rule == FRONT_RULE_ALL_FRONTS else []
      extra = ["owner_electable"] if electable else []
      tags[id(e)] = ("street_side",
                     basis if front else "geometry",
                     confidence if e.street_name else "medium",
                     second + extra)

  if front is not None and not any(t[0] == "rear" for t in tags.values()):
    # Rear = shared edge most opposite the front; near-tied scores (within
    # rear_tie_epsilon) go to the LONGEST candidate — a rear is a face, not a
    # stub.
    best = -math.inf
    scores: List[Tuple[_RawEdge, float]] = []
    for e in shared_edges:
      if e is front:
        continue
      dot = -(e.normal[0] * front.normal[0] + e.normal[1] * front.normal[1])
      scores.append((e, dot))
      if dot > best:
        best = dot
    if best >= cfg.rear_dot_threshold:
      tied = [e for e, d in scores if d >= best - cfg.rear_tie_epsilon]
      rear = max(tied, key=lambda e: e.length_ft)
      tags[id(rear)] = ("rear", "geometry", "high", [])

  for e in shared_edges:
    if id(e) not in tags:
      tags[id(e)] = ("side", "geometry", "high", [])

  # --- 6. Assemble -----------------------------------------------------------
  edges: List[LotEdge] = []
  for e in raw_edges:
    tag, edge_basis, edge_conf, edge_flags = tags[id(e)]
    abuts = (EdgeAbuts("street", street_name=e.street_name,
                       street_name_source=e.street_name_source) if e.street
             else EdgeAbuts("parcels", apns=list(e.apns)))
    edges.append(LotEdge(
      pts=[proj.to_ll(samples[i].pt) for i in e.sample_idx],
      tag=tag,
      abuts=abuts,
      length_ft=round_half_up(e.length_ft),
      basis=edge_basis,
      confidence=edge_conf,
      flags=edge_flags,
    ))

  touching = {a for e in shared_edges for a in e.apns}
  street_names: List[str] = []
  for e in street_edges:
    if e.street_name and e.street_name not in street_names:
      street_names.append(e.street_name)

  return EdgeLabelingResult(
    edges=edges,
    flags=global_flags,
    stats=EdgeLabelingStats(len(gaps), street_names, len(touching)),
  )
