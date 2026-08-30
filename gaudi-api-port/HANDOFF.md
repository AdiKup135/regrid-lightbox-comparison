# Handoff: edge-labeling engine → Gaudi integration

Context brief for a session working in `/Users/adi/Documents/formX/repos/Gaudi`.
Everything referenced is staged in the POC repo at
`/Users/adi/Documents/formX/site/gaudi-api-port/` — **nothing in Gaudi has been
touched.** Written 2026-08-30.

## What this is

A Python port of the parcel edge-labeling engine (labels each lot edge
front / street_side / side / rear as input to setback checks), plus a merge of
the two competing front-edge approaches that existed:

- the POC engine (`site/edge-labeling/edge-labeling.ts`, spec'd in FOR-1309) —
  parcel-fabric abutment analysis + jurisdiction front rules;
- Tom's production frontend detector (`gaudi/src/services/zoneomics.ts::detectFrontEdgeIndex`) —
  Google Roads API street naming.

The merge keeps the pipeline (abutment is proven by the parcel fabric) and
adopts Roads as a higher-precedence *naming oracle*, injected, with the
neighbour-address census as offline fallback.

## Considerations already weighed (do not re-litigate without new facts)

### Repo topology and contracts
- `gaudi-api` is the production backend: Python 3.12, Flask, `routes → services → models`.
  Read `AGENTS.md` in its prescribed order before editing; testing rules live in
  `.agents/rules/testing.md` (unit + real-process endpoint E2E; Flask test
  client ≠ E2E). Conventions: 2-space indent, `.pep8` 140 cols, plain functions
  over classes, no `print()` in request paths (use `FX_Logger` / `g.fx_logger`),
  branches `for-<n>-<slug>`, commits `FOR-<n>: <summary>`, PRs target `dev`.
- Deciding the legal front is zoning computation → belongs in `gaudi-api`
  services, not the browser. The TS-in-frontend original was a structural
  accident of the POC, not a choice to preserve.
- `VITE_ZONEOMICS_API_KEY` / `VITE_GOOGLE_API_KEY` are baked into the shipped
  browser bundle today — moving the calls server-side is also a key-hygiene fix.

### The port (drop-in ready)
- `services/compute/parcel_edges/{geometry,street_names,street_naming,edge_labeling}.py`
  + `tests/unit/services/test_edge_labeling.py` mirror gaudi-api's layout —
  copy in as-is. `cli.py` and `verification/` are POC debug tools, NOT part of
  the drop-in. No new dependencies (Shapely 2.1.2 and requests already pinned).
- **Proof of equivalence:** `verification/run.sh` diffs the Python port against
  the TS reference field-by-field — 101 cases / 412 edges / 0 differences,
  covering all tags, bases, confidences, and all flags. Re-run after touching
  either engine while both exist.
- Deliberate implementation decisions: local equirectangular projection kept
  (measured ~2.5 ms per 20-neighbour lookup; pyproj adds nothing but a
  dependency — `geometry.make_projection` is the single seam if State Plane is
  ever required); `round_half_up` replaces banker's rounding; internal
  dataclasses use `eq=False` because edges are keyed by identity — do not
  "clean up" to value equality.
- Known limitation carried over on purpose: unit-suffixed house numbers leak
  through the situs parser (`"1234-B El Camino Real"` → `"1234-b el camino"`),
  identical in both engines, pinned by a named test. Fixed in practice by the
  `subject_street_name` input (below), not by changing the parser.

### The merge (implemented + tested, 49 unit tests)
- `EdgeLabelingInput.street_namer` — optional injected callable
  (`street_naming.make_google_roads_namer`): ONE batched `nearestRoads` call per
  lookup for all frontage-section midpoints, one geocode per DISTINCT placeId
  through an injectable cache (pass a persistent one in production), snaps
  beyond 60 ft rejected (else a shallow lot's rear edge claims the front
  street). Roads name wins per section; census fills silences; a throwing or
  wrong-length namer flags `street_namer_failed` and degrades to census-only.
- `EdgeLabelingInput.subject_street_name` — the Google Places `route` already
  persisted at `Project.address['street']` (`ProjectAddressSchema`, parsed by
  `gaudi/src/utils/address.ts::parseAddressComponents`). Outranks situs parsing;
  zero new API calls.
- `street_names.py` is the ONE normalizer for every producer (situs, route,
  Roads): suffixes AND directionals canonicalized but KEPT, exact-match only.
  This deliberately rejects the frontend `normalizeStreet`'s four false-positive
  classes (substring containment, suffix-strip collisions, directional-strip
  collisions, empty-key matches-everything) — all pinned by tests.
- Street edges carry `streetNameSource: 'roads' | 'census'` (additive field;
  the differential comparator whitelists it).

### Existing Gaudi code this collides with
- `detectFrontEdgeIndex` + `buildSetbackGeoJSON` + `offsetPolygon` +
  `geocodeStreetName` + `roadNameForPlaceId` (frontend zoneomics.ts): their
  output `setbackGeoJSON` is **dead code** — the sole caller
  (`ProjectInfoModal.tsx:208`) destructures `{ zoning }` and drops it, and it
  burns Geocoding + Roads quota per lookup producing it. Recommendation: delete
  rather than port; serve labeled edges from gaudi-api when the map needs them.
  Verify first (it's an absence claim): `grep -rn "setbackGeoJSON" gaudi/src`.
- `parcelGeoJSON` IS live (persisted in `Project.zoneomics_data`, drawn by
  `ViewerActions.tsx:112`) — leave it alone.
- `gaudi-api/sheets/zoneomics_client.py` deliberately never ported the parcel
  geometry ("UI-only map-drawing logic") — the backend seam is clean. Mimic its
  best-effort error style (degrade to None, `_log_error` via fx_logger).

### Zoneomics API facts (verified live 2026-08-30 — do not re-spend quota rediscovering)
- Area queries (radius or bbox) NEVER return parcel `boundary` — only
  address/point queries do. The 2+N call pattern is irreducible.
- bbox search is INTERSECT-based; radius search is CENTROID-based. Neighbour
  discovery should be bbox-first (subject extent + ~15 m margin) — already
  wired in the POC's `zoneomics-backend /edges`, with radius fallback.
- `/v2/tiles` (MVT) carries a single `zones` layer — no parcels, no road names,
  and no ROW mask (zone polygons cover the streets; verified in Palo Alto).
  Zoning overlay only. Tile calls did not count against the zoneDetail quota.
- The `boundary` WKT request param rejects standard `POLYGON((…))`; format
  undocumented. The public sandbox (sandbox-api.zoneomics.com, Redondo Beach
  only) proxies auth through their site — not directly scriptable.
- **Quota state:** account credits were exhausted 2026-08-30 (overage disabled).
  Failure mode to design against: the old code treats 429s as "no neighbours",
  silently mislabeling the lot as an unnamed through lot. The POC backend now
  has a `ZONEOMICS_CALL_BUDGET` guard (default 40/process, 0 = offline-only) +
  offline fixtures; a distinct `neighbor_fetch_failed` flag is proposed but NOT
  yet implemented anywhere.

### Jurisdiction data + product context
- `site/zoning-ordinances/zoning_ordinance_links.json` — 23 jurisdictions,
  front_rule + overrides, all code-cited; language-neutral, moves as-is.
  Rule mix: shortest_frontage 11 · owner_elected 5 · designated 4 · all_fronts 2
  · address_street 1 — i.e. address-street matching alone is legally correct in
  1 of 23; jurisdiction rules are not optional polish.
- Engine default for unlisted cities: address_street, falling back to shortest
  frontage; unevaluable overrides also fall back to address_street +
  `front_rule_override_unevaluated`. Counsel-facing summary of all rules:
  `site/zoning-ordinances/front-rule-summary.pdf` (approved via Slack 👍 flow).
- `second_front` flag is load-bearing for the downstream setback engine
  (all_fronts jurisdictions): a `street_side` edge with `second_front` must get
  FRONT setback rules.
- Linear FOR-1309 documents the logic and now carries an "Optimization notes"
  section keyed to its steps (marked ✅ staged / ◻ open). Assignee: Tom.

## Added 2026-08-30: the free ("opendata") data provider

After the quota burn, the Zoneomics fetch orchestration was rebuilt on free
sources, in Python, in this staging tree — it produces the exact `/edges` wire
shape, so the engine and UI are unchanged. New, all gaudi-convention code:

- `services/parcel_data/` — clients styled on `sheets/zoneomics_client.py`
  (never raise, degrade to None): `google_geocoder_client` (primary address
  oracle when a key exists; also yields the `route` → `subject_street_name`),
  `census_geocoder_client` (the authoritative point→jurisdiction/county
  containment lookup ONLY — its address-matching endpoint and the situs
  string-matching that compensated for it were removed 2026-08-30 as
  unreliable; Google or a caller lat/lng is required), `arcgis_parcel_client`
  (county-agnostic parcel queries; neighbors in ONE envelope call vs
  Zoneomics' 2+N; situs joins for geometry-only fabrics, ArcGIS or Socrata),
  `ca_zoning_client` (OPR statewide zoning, vintage flagged),
  `county_registry` (6 county configs = all 23 jurisdictions),
  `front_rules` (jurisdiction db lookup by zoneomics_city_id OR name),
  `fetch_parcel_context` (the use case; caller-lat/lng or Google geocode, then
  parallel containment/parcel/zoning fetches through a shared Session; the
  subject is simply the parcel containing the rooftop point — a miss fails
  loudly as no_parcel; every degradation a flag — `neighbor_fetch_failed` is
  implemented here).
- `routes/parcel_edges.py` — the Flask assembly this doc's next section said
  was "left to the Gaudi side": `GET /edges` + `POST /edges/label`. Drop-in
  minus `@login_required` and the GOOGLE_API_KEY env read (→ config.py).
- `app_poc.py` — POC-only dev server (port 3004, `npm run dev:opendata`);
  binds an fx_logger-shaped shim so the shared modules run in both worlds.
- `tests/unit/services/parcel_data/` + `tests/unit/routes/` — 53 offline tests
  (URL-routed fake transport). Suite total 102, all green.

Gaudi integration deltas beyond the engine drop-in: copy `services/parcel_data/`
verbatim; copy the route + add auth + register in `application.py`; move the
GOOGLE_API_KEY read into config.py (a Google Maps key already exists there —
hardcoded at config.py:144, worth rotating to env while you're in the file);
in production prefer passing `Project.address`'s persisted lat/lng + street to
`fetch_parcel_context(lat=, lng=, ...)` — zero geocoding calls per lookup.

## Not done, deliberately left to the Gaudi side
- ~~Flask route/blueprint wiring, request parsing, auth, response mapping~~ —
  done above for the opendata path; only auth + registration remain.
- The ZONEOMICS fetch orchestration as a gaudi-api adapter — now optional: the
  opendata provider covers the same contract from free sources. The Express
  `/edges` remains the Zoneomics reference (bbox discovery, APN cache, call
  budget) if that provider is ever wanted server-side.
- Endpoint E2E tests (required by gaudi-api's testing contract once a route exists).
- Decision: delete vs. keep Tom's frontend detector (recommendation: delete —
  see dead-code note above).
- Persistent placeId→route cache choice (diskcache/pg — gaudi-api has both
  patterns available).
- Retirement plan for the TS reference in `site/` once the Python engine is
  live (keep the differential harness until then).
