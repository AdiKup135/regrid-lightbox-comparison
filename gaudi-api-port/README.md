# gaudi-api drop-in: parcel edge labeling (Python port)

A Python port of `site/edge-labeling/edge-labeling.ts`, laid out to mirror
`gaudi-api`'s own directory structure so it can be copied in as-is.

**Nothing in the Gaudi repo has been touched.** This is a staging copy in the
`site` repo. Integration is a deliberate act by a Gaudi dev, not something that
has already half-happened.

## What goes where

Copy these paths into `gaudi-api/`, preserving the layout:

| From (here) | To (`gaudi-api/`) |
| --- | --- |
| `services/compute/parcel_edges/` | `services/compute/parcel_edges/` |
| `services/parcel_data/` | `services/parcel_data/` (the free data provider — see HANDOFF.md) |
| `routes/parcel_edges.py` | `routes/parcel_edges.py` (+ `@login_required`, + register in `application.py`) |
| `tests/unit/services/test_edge_labeling.py` | `tests/unit/services/test_edge_labeling.py` |
| `tests/unit/services/parcel_data/` | `tests/unit/services/parcel_data/` |
| `tests/unit/routes/test_parcel_edges.py` | `tests/unit/routes/test_parcel_edges.py` |

Do **not** copy `pytest.ini` (gaudi-api has its own, and its `pythonpath = . sheets`
already covers these imports), `verification/` (a dev tool, see below), or
`app_poc.py` (the site repo's throwaway Flask dev server, port 3004).

No new dependencies: the port uses **Shapely 2.1.2**, already pinned in
`requirements.txt`, plus the standard library.

```bash
# from gaudi-api/, after copying
python -m pytest tests/unit/services/test_edge_labeling.py -q
```

## The module

```
services/compute/parcel_edges/
  __init__.py
  geometry.py       # projection, WKT parsing, planar primitives (Shapely-backed)
  street_names.py   # THE street-name normalizer: one key, exact-match compare
  street_naming.py  # Google Roads API namer (optional, injected; uses requests)
  edge_labeling.py  # types + the labeling pipeline; label_edges() is the entry point
  cli.py            # stdin/stdout runner for the site repo's debug UI — NOT part of the drop-in
```

```python
from services.compute.parcel_edges.edge_labeling import (
  EdgeLabelingInput, FrontRuleOverride, ZoneomicsParcel, label_edges,
)

result = label_edges(EdgeLabelingInput(
  subject=ZoneomicsParcel(apn=..., address=..., lat=..., lng=..., boundary=wkt),
  neighbors=[...],
  front_rule=record["front_rule"]["rule"],                 # from the jurisdiction db
  front_rule_overrides=[FrontRuleOverride.from_db(o)
                        for o in record["front_rule"].get("overrides", [])],
  zone=zone_details,                                       # feeds override conditions
))
result.to_dict()   # JSON-ready, identical shape to the TypeScript output
```

`label_edges` is pure: no I/O, no config reads, no globals. It belongs under
`services/` and should be called from a route, never the other way round.

### Street naming: two evidence sources, merged

A road gap's street name now comes from the best of two sources, per section:

1. **Google Roads API** (`street_naming.make_google_roads_namer`) — names the
   road that actually runs along the frontage. ONE batched `nearestRoads` call
   per lookup (all section midpoints at once), one Geocoding call per *distinct*
   `placeId` through an injectable cache, and a `max_snap_ft` ceiling so a rear
   edge on a shallow lot cannot claim the front street. Injected via
   `EdgeLabelingInput.street_namer`; the engine never imports it.
2. **Neighbour-address census** — the original mechanism; free, offline, and
   the proof of ABUTMENT stays with the parcel fabric either way. Fills every
   section the namer leaves unnamed, so no key / no quota degrades gracefully
   (a throwing or wrong-length namer flags `street_namer_failed` and falls back
   whole).

Every street edge reports `streetNameSource: 'roads' | 'census'` so a reviewer
can see which oracle spoke. The subject's own street can be passed as
`subject_street_name` (the Google Places `route` already stored on the project
record) — it outranks parsing the situs address and settles unit-suffixed house
numbers ("1234-B") for the subject outright.

`street_names.py` is the single normalizer both sides share. It canonicalizes
suffixes and directionals but KEEPS them, and matching is exact equality — the
four false-positive classes in the frontend's `normalizeStreet` (substring
containment, suffix collisions, directional collisions, empty-key match-all)
are each pinned by a unit test.

## Verified against the reference implementation

`verification/run.sh` bundles the TypeScript engine with esbuild, runs both
engines over identical generated fixtures, and diffs every field of every edge.

Current status: **101 cases, 412 edges, 0 differences.** (`streetNameSource`
is a whitelisted additive field — the port emits it, the reference never did.) Coverage spans all four
tags, all five `basis` values, all three confidence levels, and all eleven lot
and edge flags — including `attribution_gap`, `boundary_spike`, `through_lot`,
`second_front`, and both override outcomes (`applied` / `unevaluated`).

Fixtures include mid-block, corner, through, landlocked, oversized-corner,
cul-de-sac (arc frontage stays one edge), rounded block corner with no street
names (geometric fallback), survey spikes on shared boundaries, anonymous
neighbours, every front rule, every owner-election index, and 40 seeded random
quadrilaterals.

Re-run it after any change to either engine while both exist. Delete
`verification/` once the TypeScript version is retired.

## Port decisions worth a reviewer's attention

1. **Shapely replaces the hand-rolled geometry** for WKT parsing,
   point-in-polygon, and point-to-boundary distance (`geometry.Ring` holds one
   ring as both a vertex list and Shapely geometry so the two cannot drift).
   The manual `distPtSeg`/`distPtRing`/`pointInRing` helpers are gone.
   One semantic difference: Shapely's `contains` excludes points exactly on the
   boundary, where the even-odd test was arbitrary. Every caller probes points
   offset by whole feet, so this never arises — and it is confirmed by the
   zero-diff run above.

2. **The projection stays a local equirectangular approximation** — measured,
   not assumed. A full lookup with 20 neighbours runs in **~2.5 ms**, and the
   projection does not appear anywhere in the profile's top 14 entries; the cost
   is Shapely `Point` construction. Two multiplications per point, no dependency
   (`pyproj` is not in `requirements.txt`), and an error far below the sub-foot
   tolerances used here — this is already the most efficient option, and it is
   noise next to the 2+N Zoneomics HTTP calls that feed it. Leave it alone.
   `geometry.make_projection` is the single seam if a future requirement ever
   demands true State Plane coordinates.

3. **`round_half_up`** replaces Python's built-in `round`, which is banker's
   rounding and would report different edge lengths than the reference for
   exact halves.

4. **Identity semantics preserved.** The TypeScript keys edges and sections by
   object identity (`Map<RawEdge, ...>`), so the internal dataclasses use
   `eq=False` and the tag map is keyed by `id()`. Do not "clean this up" into
   value equality — two distinct edges can carry identical numbers.

5. **Field naming.** Python fields are snake_case per house style; `to_dict()`
   emits the original camelCase wire shape (`lengthFt`, `streetName`,
   `roadGaps`) so existing consumers are unaffected. Pick one at the route
   boundary.

6. **Indentation is 2-space**, matching the prevailing style in
   `services/compute/`.

## Integration findings (read before wiring this up)

Two things turned up while checking how this fits gaudi-api. Neither blocks the
drop-in; both affect what you build on top of it.

### 1. The clean street name is already in the database

`extract_street_name` exists because Zoneomics hands us one flat address string
per parcel. The subject parcel does not need it: Google Places already parses
`route` -> `street` in `gaudi/src/utils/address.ts::parseAddressComponents`, and
that lands server-side in `Project.address` (JSONB) as
`ProjectAddressSchema.street` (`gaudi-api/models/schemas/projects.py:9`). So
`project.address['street']` is an authoritative street name available with **no
new API call**, and it fixes the `"1234-B"` case for the subject outright.

It does **not** remove the parser. The census names each road gap from the
*neighbours'* addresses, which come from the Zoneomics radius pull, not from
Google — geocoding ~20 neighbours per lookup is not worth the cost or latency.
So the two sides must still be normalized the same way before they are compared:
feed the Google `street` through the same normalizer as the neighbour addresses
rather than comparing a raw `route` against a parsed key.

Beware there are already **three** different street normalizations in play:

| Where | `"El Camino Real"` becomes | Behavior |
| --- | --- | --- |
| this port's `extract_street_name` | `el camino real` | keeps the suffix |
| `gaudi/src/services/zoneomics.ts::normalizeStreet` | `elcamino` | strips suffixes (incl. `real`), directionals, punctuation |
| Google `route` component | `El Camino Real` | raw |

Picking one shared normalizer is a small change with real correctness upside —
and it is the right place to fix the `"1234-B"` limitation, once, for both sides.

### 2. gaudi already ships a front-edge detector

`gaudi/src/services/zoneomics.ts::detectFrontEdgeIndex` picks a front edge today:
Google Roads API `nearestRoads` on edge midpoints, resolve each `placeId` to a
route name, match against the address street, and fall back to nearest road, then
to `longestEdgeIndex`. It feeds `buildSetbackGeoJSON`/`offsetPolygon` for the
project-setup map.

This engine supersedes that: it labels *every* edge (front / street_side / side /
rear) from the parcel fabric, applies the per-jurisdiction front rule and its
conditional overrides, and reports `basis`, `confidence`, and flags — where the
existing detector returns one index with no jurisdiction awareness and a
longest-edge guess when Google is silent. They will disagree on corner lots,
which is exactly the case the jurisdiction rules exist for.

**Its output is currently dead code.** `buildSetbackGeoJSON` returns
`setbackGeoJSON`, and that name appears nowhere in the `gaudi` repo outside
`services/zoneomics.ts` itself — the sole caller
(`ProjectInfoModal.tsx:208`) destructures `{ zoning: fetched }` and drops it.
Contrast `parcelGeoJSON`, which *is* live: it rides along on `zoning`, is
persisted into `Project.zoneomics_data`, and is drawn by
`ViewerActions.tsx:112` as the "parcel" overlay. So the parcel outline renders;
the setback polygon and its front-edge choice are computed and discarded.

That is worth knowing twice over:

- **It makes the replacement cheap.** Nothing renders from the front edge today,
  so there is no UI to keep in sync and no visual regression to guard against.
  The clean move is to delete `detectFrontEdgeIndex`, `classifyByForwardNormal`,
  `offsetPolygon`, `buildSetbackGeoJSON`, `geocodeStreetName`, and
  `roadNameForPlaceId` rather than port them, and to serve labeled edges from
  gaudi-api when the map is ready to draw them.
- **It is costing live Google quota for nothing.** Each zoning lookup where any
  setback is greater than zero spends one Geocoding call
  (`geocodeStreetName`) plus one Roads API `nearestRoads` call, plus a Geocoding
  call per distinct edge `placeId` (module-lifetime cached), to produce a value
  no one reads.

Verify both claims before acting — the greps are
`grep -rn "setbackGeoJSON" gaudi/src` and `grep -rn "parcelGeoJSON" gaudi/src`.

`gaudi-api/sheets/zoneomics_client.py` deliberately did *not* port that geometry
("UI-only map-drawing logic"), so nothing on the backend depends on it either.
The seam is completely clean.

### 3. Zoneomics API facts, established empirically (2026-08-30)

Verified against the live API before quota ran out; the tile probe is
repeatable via `verification/probe_tiles.py`:

- **Area queries never return parcel boundaries.** `output_fields=parcels` with
  `radius` or a bbox returns centroids/APNs/addresses only; `boundary` comes
  back solely from address/point queries. The 2+N call pattern is irreducible
  with this API.
- **The bbox query is INTERSECT-based; the radius query is CENTROID-based.** A
  large bordering parcel whose centroid sits beyond the radius is dropped by
  radius and caught by bbox. Neighbour discovery should be bbox-first (subject
  extent + ~15 m margin); the site repo's `/edges` route now does this, radius
  kept as fallback.
- **Vector tiles (`/v2/tiles`) carry a single `zones` layer** — zoning polygons
  with `zone_code/zone_name/zone_type/zone_sub_type` only. No parcel layer, no
  road names, and no right-of-way mask either: zone polygons cover the streets
  (verified by probing outward from a real parcel's frontage — all probes landed
  inside zones). Tiles are useful for a zoning overlay, nothing else here.
- The WKT `boundary` request parameter rejected a standard `POLYGON((...))`
  string; its expected format is undetermined (probe stopped by quota).

## Known limitation, carried over deliberately

A unit-suffixed house number (`"1234-B El Camino Real"`) is not recognized as a
number and leaks into the street key, yielding `"1234-b el camino"` instead of
`"el camino real"`. The reference implementation does exactly the same — verified
by running both. It only matters when one neighbour on a street carries a unit
suffix and another does not. Fixing it changes labeling behavior and so belongs
in its own change, not in a port whose whole value is being provably identical.
`tests/unit/services/test_edge_labeling.py::test_unit_suffixed_house_number_is_not_stripped`
pins the current behavior so a future fix is a deliberate, visible edit.

## Not included

- Route/blueprint wiring, request parsing, auth, and response mapping — the
  `routes/` layer is owned by gaudi-api and its contracts are its own call.
- The Zoneomics fetch sequence (address query, radius query, per-neighbour
  boundary pulls, caching by APN). The TypeScript file's trailing `USAGE` block
  sketches it; it is I/O and belongs in an adapter, not in this pure module.
- Endpoint E2E tests. gaudi-api's testing standard requires them for
  endpoint-owned behavior; there is no endpoint here yet.
- Any scoped `AGENTS.md`. Repo policy is gaudi-api's to write.

## Provenance

Ported from `site/edge-labeling/edge-labeling.ts` (902 lines) against
`site/edge-labeling/SPEC.md`. The jurisdiction front-rule data it consumes lives
in `site/zoning-ordinances/zoning_ordinance_links.json` and is language-neutral —
it moves as-is. The legal reading encoded by those rules is summarized for
counsel in `site/zoning-ordinances/front-rule-summary.pdf`.
