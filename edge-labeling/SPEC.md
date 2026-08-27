# Parcel edge labeling — spec

Labels each edge of a subject parcel as **front / street_side / side / rear** using only Zoneomics data. Implementation: `edge-labeling.ts` (self-contained TypeScript, no dependencies — copy the file (plus the jurisdiction db, `zoning-ordinances/zoning_ordinance_links.json`) into any repo). This module does not compute setback values; the rules engine consumes its labels downstream.

## Terminology

| Tag | Meaning |
|---|---|
| `front` | The primary street frontage |
| `street_side` | Street-facing but not the front (corner lots) |
| `side` | Shared with neighboring parcel(s) |
| `rear` | The edge most opposite the front |

Flat label set — no subtags. `street_side` is the canonical term (the most common phrasing across the surveyed codes; "exterior side" is an input alias only).

## Inputs

1. **Subject + neighbor parcels** from Zoneomics `zoneDetail` (Enterprise `parcels` output):
   - address query → subject parcel with `boundary` WKT;
   - radius query (60 m) → neighbor **centroids only** (GeoJSON `features[0].properties.parcels[]`);
   - one point query per neighbor centroid → its boundary. ~2 + N calls per address; parallelize and cache by APN.
   - `parcels[].lat/lng` is the exact polygon centroid; the top-level address geocode is rooftop-style and is never used to pick the front.
2. **`frontRule`** for the jurisdiction, looked up in the unified jurisdiction db (`zoning-ordinances/zoning_ordinance_links.json`, `front_rule.rule` per record) by Zoneomics `city_id`: `shortest_frontage | address_street | designated | owner_elected | all_fronts`. The db lives outside the module by design; unlisted jurisdictions default to `address_street`.
3. Optional **user election** of the front edge (`userFrontOverrideEdgeIndex`) — legally meaningful where the rule is `owner_elected`.

## Algorithm (identity over geometry)

1. **Parse + project** — WKT outer ring → local tangent plane (ft). Consecutive survey-noise vertices closer than `vertexDedupeFt` (0.5 ft) are merged. The boundary is sampled at 5 ft *only to measure* who is across it; sampling never creates edge breaks.
2. **Attribution** — a sample belongs to a neighbor when it lies within `snapToleranceFt` (1.0 ft) of that neighbor's boundary; unowned samples are street candidates.
   - **Gap triage (probe, not width):** every unowned stretch is probed a few feet outward along the boundary's outward normal (`gapProbeFt`, 8 ft, at three stations). Probe points landing *inside a neighbor polygon* mean the void is a parcel-fabric sliver → the stretch is absorbed into the shared chain + `attribution_gap` flag; open space means real right-of-way → street, regardless of the stretch's length (a 6-ft frontage on an alley stays a street).
3. **Census** — road gaps = the surviving unowned stretches. Each gap's straight sections (≥ 25 ft) get a street name by matching neighbors whose boundaries run along the same street line and reading their address street names.
4. **Build edges.** Breaks occur only at:
   - street ↔ neighbor transitions;
   - true corners inside shared stretches. **Corner test:** direction is measured over `armLengthFt` (10 ft) of boundary on *each side* of a vertex — never between adjacent samples, which is noise on densely digitized fabrics. A corner exists only inside the band `cornerMinDeg ≤ Δ < cornerMaxDeg` (45°–170°); a near-reversal ≥ 170° is a fabric spike → no split + `boundary_spike` flag;
   - a census-confirmed street split inside one gap: when a gap carries **two street names** (corner lot), it is split once, at the boundary point nearest the **virtual corner** (intersection of the two frontage lines — the angle-bisector crossing for a rounded fillet).
   - Consequences: a change of neighbor along a straight line does **not** break an edge (the edge lists all abutting APNs); a curved single-street frontage (cul-de-sac) stays **one** edge.
   - Adjacent edges share one vertex (road gaps are extended to the corner pins on both ends), so the edges tile the entire boundary — no unlabeled segments; edge lengths sum to the perimeter.
5. **Label — single pass.** All evidence exists before any tag is assigned; the front is decided once, never revised. The **jurisdiction rule is the dispatcher** — it selects the method (state law never overrides front designation; it only softens front-setback consequences downstream, in the rules engine):
   - exactly one street edge → front, regardless of rule (mid-block and cul-de-sac lots);
   - `shortest_frontage` → shortest street edge (high; medium when the addressed street disagrees);
   - `address_street` → the street edge matching the situs address (high; else shortest + low + review flag);
   - `owner_elected` → the user's election if made (high); default = addressed street else shortest (medium/low), street edges flagged `owner_electable`;
   - `designated` → best guess (addressed else shortest), low + review flag;
   - `all_fronts` → addressed else shortest tagged front for orientation (medium) + `second_front_jurisdiction` flag.
   Remaining street edges → `street_side` (or `rear` + `through_lot` if opposite the front). Rear = shared edge most anti-parallel to the front; candidates within `rearTieEpsilon` (0.1) of the best score tie and the **longest** wins — a rear is a face, not a stub (triangular lots may have none). Everything else → `side`. Zero street edges → `no_street_frontage` flag, best-guess front, low confidence.
   All tunables (`snapToleranceFt`, `vertexDedupeFt`, `armLengthFt`, `cornerMinDeg`/`cornerMaxDeg`, `gapProbeFt`, `rearTieEpsilon`, …) live in one config block at the top of the module for fine-tuning.
6. **Output** — `LotEdge[]`: `pts`, `tag`, `abuts` (street name or APN list), `lengthFt`, `basis` (`single_frontage | address_match | jurisdiction_rule | geometry | user_override`), `confidence`, `flags`; plus lot-level flags and stats (road gaps, street names, neighbors touching). Consumers read tags + confidence — never re-derive geometry. UI should make the front flippable when flagged `owner_electable`.

## Prior art this follows

- Esri ArcGIS Urban "Set Edge Info On Parcels": same edge taxonomy; front picked by street ranking; ships an editable edges layer (human override is expected).
- ET GeoWizards street frontages: street = boundary not duplicated by a neighboring parcel.
- CGAL 2D straight skeleton: angle-bisector partitioning — the corner-split construction here, and the machinery the setback-envelope module will want for offsetting.

## Test fixtures (all passing)

| Case | Expected |
|---|---|
| Mid-block lot, shallow bend in rear line | 4 edges; the bent rear stays one edge |
| Square corner lot, two street names | Split at the corner; front = addressed street (`address_match`); other = street_side; `owner_electable` flags under owner_elected rule |
| Cul-de-sac arc, one street | The whole arc = ONE front edge; no street_side |
| Straight boundary shared by two neighbors | ONE edge listing both APNs |
| L-bend shared boundary | Splits rear from side |
| Straight rear with survey-noise vertices + 20-ft attribution hole | ONE full-length rear edge, both APNs, `attribution_gap` flag |
| Real 20-ft alley behind the lot | Stays a street edge → `rear` + `through_lot`; no absorption |

Live-verified: 804 Lennox Ct, Sunnyvale (cul-de-sac → single front; two-neighbor rear line → one rear edge) and 1590 Madrono Ave, Palo Alto (corner → front madrono / street_side miramonte via address match; front rule owner_elected from the dictionary).
