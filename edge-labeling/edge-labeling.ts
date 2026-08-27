/**
 * ============================================================================
 * PARCEL EDGE LABELING
 * ============================================================================
 * Labels each edge of a subject parcel as front / street_side / side / rear,
 * using only Zoneomics data. Self-contained TypeScript, no dependencies:
 * copy this file into any repo and call `labelEdges(input)`.
 *
 * Approach (identity over geometry):
 *  1. Attribute the boundary: sample who is across each stretch — a neighbor
 *     parcel or nothing (nothing = street right-of-way).
 *  2. Census the surroundings: how many separate road gaps, and which street
 *     name(s) the neighbors along each gap carry.
 *  3. Build edges: breaks occur ONLY at street/neighbor transitions, at sharp
 *     corners inside shared stretches, and at census-confirmed street splits
 *     inside a road gap (split at the virtual corner / bisector crossing).
 *     A change of neighbor along a straight line does NOT break an edge; a
 *     curved single-street frontage (cul-de-sac) stays ONE edge.
 *  4. Label in a single pass: the front is decided once, from the first
 *     evidence source that yields an answer, and never revised.
 *
 * The per-jurisdiction front-declaration method lives OUTSIDE this module in
 * jurisdiction-front-rules.json (keyed by Zoneomics city_id). The caller
 * looks the rule up and passes it in as `frontRule`.
 *
 * This module does not compute setback values — that is the rules engine's
 * job, downstream of these labels.
 * ============================================================================
 */

/* ============================================================================
 * SECTION 1 — INPUT
 * ============================================================================
 * Three zoneDetail call shapes feed this module (Enterprise `parcels` output):
 *  (1) address query  -> subject parcel WITH `boundary` WKT (data.parcels[0])
 *  (2) radius query   -> nearby parcel centroids, NO boundaries
 *                        (data.features[0].properties.parcels[])
 *  (3) point query per neighbor centroid -> that parcel WITH boundary.
 *      ~2 + N calls per address; run in parallel, cache by APN.
 * Notes: parcels[].lat/lng is the exact polygon centroid. The top-level
 * address geocode is rooftop-style (an interior point) — never used here.
 */

/** One parcel, exactly as it appears in zoneDetail -> data.parcels[]. */
export interface ZoneomicsParcel {
  apn: string;
  /** Situs address, e.g. "804 Lennox Ct Sunnyvale CA" — street names feed
   *  the census that identifies which street each road gap belongs to. */
  address: string;
  /** Parcel centroid. */
  lat: number;
  lng: number;
  /** WKT MULTIPOLYGON, EPSG:4326 (lng lat order). */
  boundary: string;
}

/**
 * How the jurisdiction declares which frontage of a multi-street lot is the
 * legal front. Comes from jurisdiction-front-rules.json — never hardcoded.
 */
export type FrontRule =
  | 'shortest_frontage' // shortest street edge is the front
  | 'address_street'    // front = the street the situs address is on
  | 'designated'        // an authority or physical test designates it — not
                        //   computable here: best guess + low confidence
  | 'owner_elected'     // owner may choose — compute a default, honor the
                        //   user's election, flag street edges as electable
  | 'all_fronts';       // every street frontage is front-type; one is still
                        //   tagged front (addressed street) and the rest
                        //   street_side; the rules engine maps them back

export interface EdgeLabelingConfig {
  /** Max distance (ft) between the subject boundary and a neighbor boundary
   *  to consider them the same line. Parcel fabrics have small slivers. */
  snapToleranceFt: number;      // default 1.0
  /** Sampling step (ft) used only to MEASURE who is across the boundary.
   *  Sampling never creates edge breaks. */
  attributionStepFt: number;    // default 5
  /** Consecutive boundary vertices closer than this (ft) are merged at parse
   *  time — real parcel fabrics carry survey-noise micro-vertices. */
  vertexDedupeFt: number;       // default 0.5
  /** Corner test: direction is measured over this much boundary on EACH side
   *  of a vertex (never between adjacent samples, which is noise). */
  armLengthFt: number;          // default 10
  /** Corner band: the arm directions must differ by at least cornerMinDeg
   *  AND less than cornerMaxDeg to split. Below min = straight/curved line;
   *  at or above max = the boundary doubles back (spike/sliver artifact) —
   *  no split, flagged 'boundary_spike'. Sustained gentle curvature (a
   *  cul-de-sac arc) never reaches the band. */
  cornerMinDeg: number;         // default 45
  cornerMaxDeg: number;         // default 170
  /** Unowned stretch triage: probe this far (ft) outward from the boundary.
   *  Probe points landing INSIDE a neighbor polygon mean the "gap" is a
   *  parcel-fabric sliver (absorbed into the shared edge, flagged
   *  'attribution_gap'); open space means real right-of-way — a street —
   *  regardless of the stretch's length. */
  gapProbeFt: number;           // default 8
  /** Rear tie-break: candidates within this of the best anti-parallel score
   *  are tied; the longest tied candidate wins. */
  rearTieEpsilon: number;       // default 0.1
  /** A straight section of a road gap must be at least this long (ft) to
   *  take part in the street-name census. */
  minWingFt: number;            // default 25
  /** Lateral distance (ft) and direction slack (deg) for deciding that a
   *  neighbor's boundary lies along the same street line as a frontage
   *  section (the street-name census). */
  blockFaceLateralFt: number;   // default 12
  blockFaceAngleDeg: number;    // default 15
  /** An edge qualifies as rear only if its outward normal is at least this
   *  anti-parallel to the front's (dot <= -threshold). Triangular lots
   *  legitimately have no rear. */
  rearDotThreshold: number;     // default 0.3
}

export const DEFAULT_CONFIG: EdgeLabelingConfig = {
  snapToleranceFt: 1.0,
  attributionStepFt: 5,
  vertexDedupeFt: 0.5,
  armLengthFt: 10,
  cornerMinDeg: 45,
  cornerMaxDeg: 170,
  gapProbeFt: 8,
  rearTieEpsilon: 0.1,
  minWingFt: 25,
  blockFaceLateralFt: 12,
  blockFaceAngleDeg: 15,
  rearDotThreshold: 0.3,
};

export interface EdgeLabelingInput {
  subject: ZoneomicsParcel;
  /** All parcels from the radius pull except the subject (same-APN entries
   *  are skipped defensively). */
  neighbors: ZoneomicsParcel[];
  /** From jurisdiction-front-rules.json, keyed by Zoneomics city_id. */
  frontRule?: FrontRule;
  /** Owner's election of the front edge (index into the returned edges).
   *  Only meaningful where frontRule is 'owner_elected'. */
  userFrontOverrideEdgeIndex?: number;
  config?: Partial<EdgeLabelingConfig>;
}

/* ============================================================================
 * SECTION 2 — OUTPUT
 * ============================================================================ */

export interface LotEdge {
  /** Ordered vertices of this edge, [lng, lat]. */
  pts: [number, number][];
  /** front = the primary street frontage · street_side = street-facing but
   *  not the front (corner lots) · side = shared with neighbor(s) · rear =
   *  the edge most opposite the front. */
  tag: 'front' | 'street_side' | 'side' | 'rear';
  /** What lies across this edge: a street, or one or MORE neighbor parcels
   *  (a straight edge touched by two neighbors is still one edge). */
  abuts: { kind: 'street'; streetName?: string } | { kind: 'parcels'; apns: string[] };
  lengthFt: number;
  /** How the tag was decided. */
  basis: 'single_frontage' | 'address_match' | 'jurisdiction_rule' | 'geometry' | 'user_override';
  confidence: 'high' | 'medium' | 'low';
  /** e.g. 'owner_electable', 'through_lot' */
  flags: string[];
}

export interface EdgeLabelingResult {
  edges: LotEdge[];
  /** Lot-level flags: 'no_street_frontage', 'front_requires_review',
   *  'second_front_jurisdiction', 'through_lot', 'unknown_street_name'. */
  flags: string[];
  stats: { roadGaps: number; streetNames: string[]; neighborsTouching: number };
}

/* ============================================================================
 * SECTION 3 — geometry helpers (planar, ft; local tangent plane)
 * ============================================================================ */

type Pt = [number, number];

const FT_PER_DEG_LAT = 364567.2;

function makeProjection(originLng: number, originLat: number) {
  const ftPerDegLng = FT_PER_DEG_LAT * Math.cos((originLat * Math.PI) / 180);
  return {
    toFt: ([lng, lat]: Pt): Pt => [(lng - originLng) * ftPerDegLng, (lat - originLat) * FT_PER_DEG_LAT],
    toLL: ([x, y]: Pt): Pt => [originLng + x / ftPerDegLng, originLat + y / FT_PER_DEG_LAT],
  };
}

/** WKT MULTIPOLYGON/POLYGON -> outer ring of the largest polygon, without
 *  the closing duplicate vertex. */
export function parseWktOuterRing(wkt: string): Pt[] {
  const polys = wkt.match(/\(\(([^()]+)\)/g);
  if (!polys || polys.length === 0) throw new Error(`Unparseable WKT boundary: ${wkt.slice(0, 60)}...`);
  let best: Pt[] = [];
  let bestArea = -1;
  for (const p of polys) {
    const ring: Pt[] = p.replace(/[()]/g, '').split(',').map((pair) => {
      const [lng, lat] = pair.trim().split(/\s+/).map(Number);
      return [lng, lat] as Pt;
    });
    if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
    let a = 0;
    for (let i = 0; i < ring.length; i++) {
      const [x1, y1] = ring[i];
      const [x2, y2] = ring[(i + 1) % ring.length];
      a += x1 * y2 - x2 * y1;
    }
    if (Math.abs(a) > bestArea) { bestArea = Math.abs(a); best = ring; }
  }
  if (best.length < 3) throw new Error('Boundary ring has fewer than 3 vertices');
  return best;
}

const dist = (a: Pt, b: Pt): number => Math.hypot(a[0] - b[0], a[1] - b[1]);

function distPtSeg(p: Pt, a: Pt, b: Pt): number {
  const l2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2;
  if (l2 === 0) return dist(p, a);
  let t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / l2;
  t = Math.max(0, Math.min(1, t));
  return dist(p, [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
}

function distPtRing(p: Pt, ring: Pt[]): number {
  let d = Infinity;
  for (let i = 0; i < ring.length; i++) d = Math.min(d, distPtSeg(p, ring[i], ring[(i + 1) % ring.length]));
  return d;
}

function pointInRing(p: Pt, ring: Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Outward unit normal of segment ab, oriented by testing which side is
 *  outside the ring (winding-agnostic). */
function outwardNormal(a: Pt, b: Pt, ring: Pt[]): Pt {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  let nx = dy / len, ny = -dx / len;
  const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  if (pointInRing([mid[0] + nx * 2, mid[1] + ny * 2], ring)) { nx = -nx; ny = -ny; }
  return [nx, ny];
}

const dirDeg = (a: Pt, b: Pt): number => (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;
const angDiff = (x: number, y: number): number => { const d = Math.abs(x - y) % 360; return d > 180 ? 360 - d : d; };

/** Intersection of two infinite lines (point + unit direction); null if
 *  parallel. */
function lineIntersect(p1: Pt, d1: Pt, p2: Pt, d2: Pt): Pt | null {
  const det = d1[0] * d2[1] - d1[1] * d2[0];
  if (Math.abs(det) < 1e-9) return null;
  const t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / det;
  return [p1[0] + t * d1[0], p1[1] + t * d1[1]];
}

/* ============================================================================
 * SECTION 4 — street-name extraction
 * ============================================================================ */

const STREET_SUFFIXES = new Set([
  'ave', 'avenue', 'st', 'street', 'rd', 'road', 'dr', 'drive', 'blvd', 'boulevard',
  'ln', 'lane', 'ct', 'court', 'pl', 'place', 'way', 'ter', 'terrace', 'cir', 'circle',
  'hwy', 'highway', 'pkwy', 'parkway', 'aly', 'alley',
]);

const SUFFIX_CANON: Record<string, string> = {
  avenue: 'ave', av: 'ave', street: 'st', road: 'rd', drive: 'dr', boulevard: 'blvd', lane: 'ln',
  court: 'ct', place: 'pl', wy: 'way', terrace: 'ter', circle: 'cir', highway: 'hwy', parkway: 'pkwy', alley: 'aly',
};

/** "804 Lennox Ct Sunnyvale CA" -> "lennox ct". Skips the house number, then
 *  takes tokens up to and including the first recognized street suffix
 *  (suffix variants are canonicalized so "Av" == "Ave" == "Avenue"). */
export function extractStreetName(address: string): string | null {
  if (!address) return null;
  const tokens = address.trim().toLowerCase().replace(/[.,]/g, '').split(/\s+/);
  let i = 0;
  while (i < tokens.length && /^\d[\d/-]*$/.test(tokens[i])) i++;
  if (i >= tokens.length) return null;
  const name: string[] = [];
  for (let j = i; j < tokens.length && name.length < 4; j++) {
    const t = SUFFIX_CANON[tokens[j]] ?? tokens[j];
    name.push(t);
    if (STREET_SUFFIXES.has(t)) return name.join(' ');
  }
  return name.slice(0, 3).join(' ') || null;
}

/* ============================================================================
 * SECTION 5 — pipeline
 * ============================================================================ */

interface Sample { pt: Pt; isVertex: boolean; owner: string | null }
/** A straight piece of a road gap (indices are positions within the gap). */
interface Section { start: number; end: number; dir: number; lengthFt: number }
interface Gap { idx: number[]; sections: Section[]; names: Map<string, Section[]> }
interface RawEdge {
  sampleIdx: number[];
  street: boolean;
  apns: string[];
  streetName: string | null;
  lengthFt: number;
  normal: Pt;
}

export function labelEdges(input: EdgeLabelingInput): EdgeLabelingResult {
  const cfg: EdgeLabelingConfig = { ...DEFAULT_CONFIG, ...(input.config ?? {}) };
  const frontRule: FrontRule = input.frontRule ?? 'shortest_frontage';
  const globalFlags = new Set<string>();

  /* ---- 5.1 Parse, project, sample ------------------------------------------
   * The boundary is resampled at attributionStepFt purely to measure who is
   * across each stretch; original vertices are kept and marked, because only
   * vertices can become corners. */
  const proj = makeProjection(input.subject.lng, input.subject.lat);
  const ringLL = parseWktOuterRing(input.subject.boundary);
  let ring = ringLL.map(proj.toFt);
  // Merge survey-noise micro-vertices (incl. the ring wrap).
  ring = ring.filter((pt, i) => i === 0 || dist(pt, ring[i - 1]) >= cfg.vertexDedupeFt);
  if (ring.length > 3 && dist(ring[0], ring[ring.length - 1]) < cfg.vertexDedupeFt) ring.pop();
  const samples: Sample[] = [];
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length];
    samples.push({ pt: a, isVertex: true, owner: null });
    const d = dist(a, b);
    const n = Math.floor(d / cfg.attributionStepFt);
    for (let k = 1; k <= n; k++) {
      const t = k / (n + 1);
      samples.push({ pt: [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])], isVertex: false, owner: null });
    }
  }
  const N = samples.length;
  const at = (i: number) => samples[((i % N) + N) % N];

  const neighbors = input.neighbors
    .filter((n2) => n2.apn !== input.subject.apn)
    .map((n2) => {
      try { return { apn: n2.apn, address: n2.address, ringFt: parseWktOuterRing(n2.boundary).map(proj.toFt) }; }
      catch { return null; }
    })
    .filter((n2): n2 is { apn: string; address: string; ringFt: Pt[] } => n2 !== null);

  /* ---- 5.2 Attribution: who is across each sample --------------------------
   * A sample belongs to a neighbor when it lies within snapToleranceFt of
   * that neighbor's boundary. Ownership changes never create edge breaks. */
  for (const s of samples) {
    for (const n2 of neighbors) {
      if (distPtRing(s.pt, n2.ringFt) <= cfg.snapToleranceFt) { s.owner = n2.apn; break; }
    }
  }

  /* ---- 5.3 Census: road gaps and their street names -------------------------
   * A road gap = a maximal contiguous stretch of unowned samples. Each gap is
   * decomposed into straight sections; each long-enough section gets a street
   * name by matching neighbors whose boundaries run along the same street
   * line and reading their address street names. */
  let rot = -1;
  for (let i = 0; i < N && rot < 0; i++) {
    if (at(i).owner !== at(i - 1).owner && (at(i).owner === null || at(i - 1).owner === null)) rot = i;
  }
  for (let i = 0; i < N && rot < 0; i++) { if (at(i).owner !== at(i - 1).owner) rot = i; }
  if (rot < 0) rot = 0;
  const order = Array.from({ length: N }, (_, k) => (rot + k) % N);

  const stretches: { owner: string | null; idx: number[] }[] = [];
  for (const i of order) {
    const cur = stretches[stretches.length - 1];
    if (cur && cur.owner === samples[i].owner) cur.idx.push(i);
    else stretches.push({ owner: samples[i].owner, idx: [i] });
  }
  if (stretches.length > 1 && stretches[0].owner === stretches[stretches.length - 1].owner) {
    stretches[0].idx = [...stretches[stretches.length - 1].idx, ...stretches[0].idx];
    stretches.pop();
  }
  // Triage unowned stretches: probe outward from the boundary; probe points
  // inside a neighbor polygon mean the stretch is a parcel-fabric sliver, not
  // a street — reassign it to the shared chain (flag 'attribution_gap').
  // Open space beyond = real right-of-way, regardless of stretch length.
  const HOLE = '__attribution_gap__';
  for (const st of stretches) {
    if (st.owner !== null || st.idx.length < 1) continue;
    const stations = [0.25, 0.5, 0.75].map((t) => st.idx[Math.min(st.idx.length - 1, Math.floor(t * st.idx.length))]);
    let insideVotes = 0;
    for (const si of stations) {
      const a = samples[si].pt;
      const b = at(si + 1).pt;
      const [nx, ny] = outwardNormal(a, b, ring);
      const hit = [cfg.gapProbeFt / 2, cfg.gapProbeFt].some((d) => {
        const q: Pt = [a[0] + nx * d, a[1] + ny * d];
        return neighbors.some((n2) => pointInRing(q, n2.ringFt));
      });
      if (hit) insideVotes++;
    }
    if (insideVotes === stations.length) {
      st.owner = HOLE;
      for (const i of st.idx) samples[i].owner = HOLE;
      globalFlags.add('attribution_gap');
    }
  }

  // Adjacent edges must share one vertex so the edges tile the full boundary:
  // each road gap is extended on both ends to the adjacent shared sample (the
  // corner pin where lot, neighbor, and street meet).
  const succ = (k: number) => stretches[(k + 1) % stretches.length].idx[0];
  const pred = (k: number) => { const st = stretches[(k - 1 + stretches.length) % stretches.length]; return st.idx[st.idx.length - 1]; };

  // Straight sections of a gap: cut where the local direction drifts away
  // from the section's starting direction.
  const straightSections = (idx: number[]): Section[] => {
    const out: Section[] = [];
    if (idx.length < 2) return out;
    let s0 = 0;
    let d0 = dirDeg(samples[idx[0]].pt, samples[idx[1]].pt);
    const close = (from: number, to: number) => {
      if (to - from < 1) return;
      let len = 0;
      for (let m = from + 1; m <= to; m++) len += dist(samples[idx[m - 1]].pt, samples[idx[m]].pt);
      out.push({ start: from, end: to, dir: dirDeg(samples[idx[from]].pt, samples[idx[to]].pt), lengthFt: len });
    };
    for (let k = 2; k <= idx.length - 1; k++) {
      const d = dirDeg(samples[idx[k - 1]].pt, samples[idx[k]].pt);
      if (angDiff(d, d0) > cfg.cornerMinDeg / 2) {
        close(s0, k - 1);
        s0 = k - 1;
        d0 = d;
      }
    }
    close(s0, idx.length - 1);
    return out;
  };

  const sectionStreetName = (idx: number[], sec: Section): string | null => {
    const p0 = samples[idx[sec.start]].pt;
    const pe = samples[idx[sec.end]].pt;
    const dlen = dist(p0, pe) || 1;
    const d: Pt = [(pe[0] - p0[0]) / dlen, (pe[1] - p0[1]) / dlen];
    const counts = new Map<string, number>();
    for (const n2 of neighbors) {
      let faces = false;
      for (let i = 0; i < n2.ringFt.length && !faces; i++) {
        const a = n2.ringFt[i], b = n2.ringFt[(i + 1) % n2.ringFt.length];
        const segLen = dist(a, b);
        if (segLen < 10) continue;
        const dirDot = Math.abs(((b[0] - a[0]) / segLen) * d[0] + ((b[1] - a[1]) / segLen) * d[1]);
        const latA = Math.abs((a[0] - p0[0]) * -d[1] + (a[1] - p0[1]) * d[0]);
        const latB = Math.abs((b[0] - p0[0]) * -d[1] + (b[1] - p0[1]) * d[0]);
        if (dirDot > Math.cos((cfg.blockFaceAngleDeg * Math.PI) / 180) && latA <= cfg.blockFaceLateralFt && latB <= cfg.blockFaceLateralFt) faces = true;
      }
      if (!faces) continue;
      const sn = extractStreetName(n2.address);
      if (sn) counts.set(sn, (counts.get(sn) ?? 0) + 1);
    }
    let best: string | null = null, bc = 0;
    for (const [k, v] of counts) if (v > bc) { best = k; bc = v; }
    return best;
  };

  const gaps: Gap[] = [];
  for (let k = 0; k < stretches.length; k++) {
    const st = stretches[k];
    if (st.owner !== null) continue;
    const idx = stretches.length > 1 ? [pred(k), ...st.idx, succ(k)] : st.idx;
    const sections = straightSections(idx);
    const names = new Map<string, Section[]>();
    for (const sec of sections) {
      if (sec.lengthFt < cfg.minWingFt) continue;
      const nm = sectionStreetName(idx, sec);
      if (nm) names.set(nm, [...(names.get(nm) ?? []), sec]);
    }
    gaps.push({ idx, sections, names });
  }

  /* ---- 5.4 Build edges -------------------------------------------------------
   * Street edges: one per road gap — unless the census found two street names
   * in one gap (corner lot with a rounded corner): then split once, at the
   * boundary point nearest the virtual corner (intersection of the two
   * frontage lines; for a fillet this is where the angle bisector crosses).
   * Shared edges: one per contiguous shared chain, split only at sharp
   * corners; each edge lists every neighbor along it. */
  const rawEdges: RawEdge[] = [];

  const finishEdge = (idxs: number[], street: boolean, streetName: string | null) => {
    if (idxs.length < 2) return;
    let len = 0, nx = 0, ny = 0;
    const apns: string[] = [];
    for (let k = 1; k < idxs.length; k++) {
      const a = samples[idxs[k - 1]].pt, b = samples[idxs[k]].pt;
      const l = dist(a, b);
      const [ox, oy] = outwardNormal(a, b, ring);
      len += l; nx += ox * l; ny += oy * l;
    }
    if (!street) {
      // A corner vertex sits within tolerance of two neighbors at once; an
      // owner must cover at least two samples of this edge to be listed.
      const counts = new Map<string, number>();
      for (const i of idxs) { const o = samples[i].owner; if (o && o !== HOLE) counts.set(o, (counts.get(o) ?? 0) + 1); }
      let maxC = 0;
      for (const v of counts.values()) maxC = Math.max(maxC, v);
      for (const [o, c] of counts) if (c >= 2 || c === maxC) apns.push(o);
    }
    const nl = Math.hypot(nx, ny) || 1;
    rawEdges.push({ sampleIdx: idxs, street, apns, streetName, lengthFt: len, normal: [nx / nl, ny / nl] });
  };

  // Shared chains: contiguous shared stretches (possibly several owners),
  // split only at sharp corners at original vertices.
  const chains: number[][] = [];
  {
    let cur: number[] = [];
    for (let k = 0; k < stretches.length; k++) {
      const st = stretches[k];
      if (st.owner === null) { if (cur.length) { chains.push(cur); cur = []; } }
      else cur.push(...st.idx); // includes absorbed attribution gaps
    }
    if (cur.length) chains.push(cur);
    // Landlocked lot (no gaps): the single chain is the whole ring — close it.
    if (chains.length === 1 && stretches.every((st) => st.owner !== null)) chains[0].push(chains[0][0]);
    // Ring wrap with no gap between the last and first stretches: one chain.
    if (chains.length > 1 && stretches[0].owner !== null && stretches[stretches.length - 1].owner !== null) {
      chains[0] = [...chains[chains.length - 1], ...chains[0]];
      chains.pop();
    }
  }
  // Corner test: direction is measured over armLengthFt of boundary on each
  // side of the vertex — never between adjacent samples, which is noise on
  // densely digitized fabrics. Splits only inside the corner band; a
  // near-reversal (>= cornerMaxDeg) is a fabric spike: no split, flagged.
  const armTurn = (list: number[], k: number): number | null => {
    let len = 0, i = k;
    while (i > 0 && len < cfg.armLengthFt) { i--; len += dist(samples[list[i]].pt, samples[list[i + 1]].pt); }
    if (len < cfg.armLengthFt * 0.6) return null;
    const dIn = dirDeg(samples[list[i]].pt, samples[list[k]].pt);
    len = 0; let j = k;
    while (j < list.length - 1 && len < cfg.armLengthFt) { j++; len += dist(samples[list[j - 1]].pt, samples[list[j]].pt); }
    if (len < cfg.armLengthFt * 0.6) return null;
    return angDiff(dIn, dirDeg(samples[list[k]].pt, samples[list[j]].pt));
  };
  for (const chain of chains) {
    let s0 = 0;
    for (let k = 1; k < chain.length - 1; k++) {
      if (!samples[chain[k]].isVertex) continue;
      const turn = armTurn(chain, k);
      if (turn === null) continue;
      if (turn >= cfg.cornerMinDeg && turn < cfg.cornerMaxDeg) { finishEdge(chain.slice(s0, k + 1), false, null); s0 = k; }
      else if (turn >= cfg.cornerMaxDeg) globalFlags.add('boundary_spike');
    }
    finishEdge(chain.slice(s0), false, null);
  }

  for (const gap of gaps) {
    const idx = gap.idx;
    const named = [...gap.names.keys()];
    if (named.length >= 2) {
      const secA = gap.names.get(named[0])![0];
      const secsB = gap.names.get(named[named.length - 1])!;
      const secB = secsB[secsB.length - 1];
      const dA: Pt = [Math.cos((secA.dir * Math.PI) / 180), Math.sin((secA.dir * Math.PI) / 180)];
      const dB: Pt = [Math.cos((secB.dir * Math.PI) / 180), Math.sin((secB.dir * Math.PI) / 180)];
      const vc = lineIntersect(samples[idx[secA.start]].pt, dA, samples[idx[secB.start]].pt, dB);
      let splitAt = Math.floor((secA.end + secB.start) / 2);
      if (vc) {
        let bd = Infinity;
        for (let k = secA.end; k <= secB.start; k++) {
          const d = dist(samples[idx[k]].pt, vc);
          if (d < bd) { bd = d; splitAt = k; }
        }
      }
      finishEdge(idx.slice(0, splitAt + 1), true, named[0]);
      finishEdge(idx.slice(splitAt), true, named[named.length - 1]);
    } else {
      finishEdge(idx, true, named[0] ?? null);
      if (!named[0]) globalFlags.add('unknown_street_name');
    }
  }

  /* ---- 5.5 Label — single pass ------------------------------------------------
   * All evidence is now available: the edges, each street edge's name, the
   * subject's own street name, the jurisdiction rule, and any user election.
   * The front is decided once and never revised. The jurisdiction rule is the
   * dispatcher: it selects HOW the front is determined (state law never
   * overrides front designation — it only softens front-setback consequences
   * downstream, in the rules engine). */
  const streetEdges = rawEdges.filter((e) => e.street);
  const sharedEdges = rawEdges.filter((e) => !e.street);
  const subjectStreet = extractStreetName(input.subject.address);
  const addressed = subjectStreet ? streetEdges.filter((e) => e.streetName === subjectStreet) : [];
  const addrMatch = addressed.length === 1 ? addressed[0] : null;
  const shortest = streetEdges.length ? streetEdges.reduce((a, b) => (a.lengthFt <= b.lengthFt ? a : b)) : null;

  let front: RawEdge | null = null;
  let basis: LotEdge['basis'] = 'geometry';
  let confidence: LotEdge['confidence'] = 'low';

  if (streetEdges.length === 1) {
    // One frontage — front regardless of rule (covers mid-block and cul-de-sac).
    front = streetEdges[0];
    basis = 'single_frontage'; confidence = 'high';
  } else if (streetEdges.length > 1) {
    switch (frontRule) {
      case 'shortest_frontage':
        front = shortest;
        basis = 'jurisdiction_rule';
        confidence = addrMatch && addrMatch !== shortest ? 'medium' : 'high';
        break;
      case 'address_street':
        if (addrMatch) { front = addrMatch; basis = 'address_match'; confidence = 'high'; }
        else { front = shortest; basis = 'geometry'; confidence = 'low'; globalFlags.add('front_requires_review'); }
        break;
      case 'owner_elected':
        // The owner's election is the rule; until made, default to the
        // addressed street (else shortest).
        if (input.userFrontOverrideEdgeIndex != null && rawEdges[input.userFrontOverrideEdgeIndex]?.street) {
          front = rawEdges[input.userFrontOverrideEdgeIndex];
          basis = 'user_override'; confidence = 'high';
        } else if (addrMatch) { front = addrMatch; basis = 'address_match'; confidence = 'medium'; }
        else { front = shortest; basis = 'geometry'; confidence = 'low'; }
        break;
      case 'designated':
        // Designated by an authority or a physical test — not computable.
        front = addrMatch ?? shortest;
        basis = addrMatch ? 'address_match' : 'geometry';
        confidence = 'low';
        globalFlags.add('front_requires_review');
        break;
      case 'all_fronts':
        // Every frontage is legally front-type; one is still tagged front so
        // rear/side orientation works. The rules engine maps street_side back.
        front = addrMatch ?? shortest;
        basis = addrMatch ? 'address_match' : 'geometry';
        confidence = 'medium';
        globalFlags.add('second_front_jurisdiction');
        break;
    }
  } else if (rawEdges.length) {
    // No street frontage: landlocked or flag lot. Guess the shortest edge as
    // the access point; the whole lot is flagged for review.
    globalFlags.add('no_street_frontage');
    front = rawEdges.reduce((a, b) => (a.lengthFt <= b.lengthFt ? a : b));
    basis = 'geometry'; confidence = 'low';
  }

  const electable = frontRule === 'owner_elected' && streetEdges.length > 1;
  const tagOf = new Map<RawEdge, { tag: LotEdge['tag']; basis: LotEdge['basis']; confidence: LotEdge['confidence']; flags: string[] }>();

  if (front) tagOf.set(front, { tag: 'front', basis, confidence, flags: electable ? ['owner_electable'] : [] });
  for (const e of streetEdges) {
    if (e === front) continue;
    const dot = front ? e.normal[0] * front.normal[0] + e.normal[1] * front.normal[1] : 0;
    if (dot < -0.5) {
      tagOf.set(e, { tag: 'rear', basis: 'geometry', confidence: 'medium', flags: ['through_lot', ...(electable ? ['owner_electable'] : [])] });
      globalFlags.add('through_lot');
    } else {
      tagOf.set(e, { tag: 'street_side', basis: front ? basis : 'geometry', confidence: e.streetName ? confidence : 'medium', flags: electable ? ['owner_electable'] : [] });
    }
  }
  if (front && ![...tagOf.values()].some((t) => t.tag === 'rear')) {
    // Rear = shared edge most opposite the front; near-tied scores (within
    // rearTieEpsilon) go to the LONGEST candidate — a rear is a face, not a stub.
    let best = -Infinity;
    const scores = new Map<RawEdge, number>();
    for (const e of sharedEdges) {
      if (e === front) continue;
      const dot = -(e.normal[0] * front.normal[0] + e.normal[1] * front.normal[1]);
      scores.set(e, dot);
      if (dot > best) best = dot;
    }
    if (best >= cfg.rearDotThreshold) {
      const tied = [...scores.entries()].filter(([, d]) => d >= best - cfg.rearTieEpsilon).map(([e]) => e);
      const rear = tied.reduce((a, b) => (a.lengthFt >= b.lengthFt ? a : b));
      tagOf.set(rear, { tag: 'rear', basis: 'geometry', confidence: 'high', flags: [] });
    }
  }
  for (const e of sharedEdges) if (!tagOf.has(e)) tagOf.set(e, { tag: 'side', basis: 'geometry', confidence: 'high', flags: [] });

  /* ---- 5.6 Assemble ------------------------------------------------------------ */
  const edges: LotEdge[] = rawEdges.map((e) => {
    const t = tagOf.get(e)!;
    return {
      pts: e.sampleIdx.map((i) => proj.toLL(samples[i].pt)) as [number, number][],
      tag: t.tag,
      abuts: e.street ? { kind: 'street' as const, streetName: e.streetName ?? undefined } : { kind: 'parcels' as const, apns: e.apns },
      lengthFt: Math.round(e.lengthFt * 10) / 10,
      basis: t.basis,
      confidence: t.confidence,
      flags: t.flags,
    };
  });

  const touching = new Set<string>();
  for (const e of sharedEdges) for (const a of e.apns) touching.add(a);

  return {
    edges,
    flags: [...globalFlags],
    stats: {
      roadGaps: gaps.length,
      streetNames: [...new Set(streetEdges.map((e) => e.streetName).filter((n): n is string => !!n))],
      neighborsTouching: touching.size,
    },
  };
}

/* ============================================================================
 * USAGE
 * ============================================================================
 * import rules from './jurisdiction-front-rules.json';
 *
 * async function labelAddress(address: string, apiKey: string) {
 *   const base = 'https://api.zoneomics.com/v2/zoneDetail';
 *   const get = async (qs: string) => (await fetch(`${base}?api_key=${apiKey}&output_fields=parcels&${qs}`)).json();
 *   const d1 = await get(`address=${encodeURIComponent(address)}`);          // subject + boundary
 *   const subject: ZoneomicsParcel = d1.data.parcels[0];
 *   const cityId = String(d1.data.meta?.city_id ?? '');
 *   const d2 = await get(`lat=${subject.lat}&lng=${subject.lng}&radius=60`); // neighbor centroids
 *   const stubs = (d2.data.features ?? []).flatMap((f: any) => f.properties?.parcels ?? [])
 *     .filter((p: any) => p.apn !== subject.apn);
 *   const neighbors = (await Promise.all(stubs.map(async (p: any) => {       // boundaries (cache by APN)
 *     const d3 = await get(`lat=${p.lat}&lng=${p.lng}`);
 *     return (d3.data.parcels ?? []).find((q: ZoneomicsParcel) => q.apn === p.apn) ?? null;
 *   }))).filter(Boolean);
 *   const frontRule = (rules as any)[cityId]?.front_rule ?? 'shortest_frontage';
 *   return labelEdges({ subject, neighbors, frontRule });
 * }
 *
 * Production notes: keep the API key server-side; cache neighbor parcels by
 * APN (same-block queries reuse them); surface `confidence` + `flags` in the
 * UI and make the front flippable when flagged 'owner_electable'.
 * ============================================================================
 */
