# Front-edge QA — engine vs FutureLot

Automated QA for the one decision the jurisdiction front rules exist to make:
**on a corner lot, which edge is the front lot line?**

It picks one corner lot in each of the 28 jurisdictions in
`zoning-ordinances/zoning_ordinance_links.json`, records what our engine says
about it, records what FutureLot says about the same lot, and reports where the
two disagree.

This directory is self-contained and **read-only with respect to the rest of the
repo**: it imports the engine and the free provider out of `gaudi-api-port/` and
the jurisdiction database out of `zoning-ordinances/`, and writes only under
`qa/front-edge/`. Nothing here is part of the gaudi-api drop-in.

## Why corner lots, and why FutureLot

A mid-block lot has one street frontage and every front rule agrees on it. A
corner lot is where the rules diverge — shortest frontage, owner election,
designated principal street, all-fronts — so it is the only specimen that
actually tests the rule. FutureLot is the closest available second opinion:
it answers the same question, for the same address, from its own data.

## Pipeline

```
seeds.json ──► find_corner_lots.py ──► data/selected.json                       (Phase A)
                                          │
                                          ├──► run_engine.py ──► data/engine_results.json     (Phase B)
                                          │
                                          └──► make_futurelot_probe.py ──► browser ──► unpack_probe.py
                                                                    └──► data/futurelot_observations.json  (Phase C)
                                                                                             │
                                                          compare.py ◄───────────────────────┘
                                                               │
                                                               └──► out/report.md · out/report.csv · data/comparison.json  (Phase D)
```

**Results of the 2026-09-01 run: [FINDINGS.md](FINDINGS.md).**

### Phase A — find one corner lot per jurisdiction (`find_corner_lots.py`)

Per jurisdiction: geocode a seed (cached on disk), pull **one** envelope of the
county parcel fabric around it, then re-run the labeling engine locally over
every parcel in that envelope — each parcel as subject, its nearest neighbours
as fabric. A parcel is a corner lot when the engine sees two street frontages
at least `CORNER_MIN_ANGLE_DEG` off parallel: not "the assessor says corner"
but "our engine believes two streets meet here", which is the condition the
front rule resolves.

Discovery is census-only — street *names* do not decide corner-ness, geometry
does — so it costs no Roads quota. The one Google call per seed is the geocode.

Candidates are ranked (two named streets, a house-numbered situs, near-right
angle, ordinary residential size) and the top few are confirmed against:

* **Census point containment** — the same authority the pipeline trusts, so the
  lot is provably inside the jurisdiction whose rule is under test. This is what
  makes the five unincorporated-county records honest: the postal city name lies
  there, the TIGER polygon does not.
* **the statewide zoning layer** — a corner in a downtown commercial district is
  the wrong specimen. A district positively readable as non-residential is
  rejected; an unreadable one is allowed through and flagged, because the
  statewide layer's `Description` is often just the code again (`R-6`, `3-DUA`)
  and a naive search for the word "residential" would silently delete whole
  counties.

```bash
python3 find_corner_lots.py                      # all 28
python3 find_corner_lots.py --jurisdiction Napa  # one
```

### Phase B — the canonical engine run (`run_engine.py`)

Discovery ran the engine in bulk to *find* lots. This runs it the way
production will, once per lot: address → `fetch_parcel_context` → `front_rule_for`
→ `label_edges` **with the Google Roads street namer**.

The lookup is by address string alone, no coordinate shortcut, because that is
what a user does and what FutureLot is given — and because it re-tests what
discovery skipped: whether a one-line address lands on the parcel we think it
does. A mismatch is recorded (`apn_match`) and the run repeated pinned to the
parcel's own coordinate, so geocode drift costs a flag rather than the case.

```bash
python3 run_engine.py
```

### Phase C — FutureLot's answer (`make_futurelot_probe.py`)

FutureLot's report page is a React app whose lot geometry arrives from a
same-origin route, `/api/street-data`, keyed by address parts plus a
coordinate. Its `lot_simplified.lot_edges` gives one entry per lot edge with
`vertexes` and an `edge_type` of front / rear / side — the numbers behind the
map labels, and directly comparable to our output. Reading that beats
screen-scraping the labels off a Mapbox canvas.

```bash
python3 make_futurelot_probe.py --start 0 --count 7 > out/probe_0.js
```

Run the probe in a browser tab signed in to `app.futurelot.com`. It issues one
GET per lot with a pause between them — the same request the page makes when
you open a report; it writes nothing and buys nothing. Two practical notes:

* The lot is resolved by **coordinate**, not by the address parts (address
  alone 404s; a coordinate alone succeeds), and the coordinate must be *inside*
  the parcel — the probe uses the polygon's representative point, since an
  L-shaped lot's centroid can land in the street.
* The browser tool truncates long return values, so slice the probe (`--start`,
  `--count`) and have the page hand back the packed form; feed that to
  `unpack_probe.py`, which restores the full observation records.

```bash
python3 unpack_probe.py data/futurelot_packed.json
```

### Phase D — the comparison (`compare.py`)

Both systems describe the same polygon, so the comparison is geometric before
it is textual: every FutureLot edge is matched to the engine edge it physically
*is* (midpoint within tolerance, near-parallel bearing), and only then are the
labels compared. That survives the two polygons not being vertex-for-vertex
identical — FutureLot serves a simplified lot; our engine merges collinear runs
and splits a frontage where a neighbour interrupts it.

It first checks the two are talking about the same parcel at all (centroid
offset, area). An address that resolves to a different lot on their side is a
finding of its own, not a labeling difference.

Two labelings are recorded per lot, and the distinction carries a finding:
**census-only** decides whether the lot is a corner (a fact about the parcel
fabric), while **the Roads-namer labeling** is what production does and what is
compared. Where they diverge the lot is flagged `roads_collapsed_frontage`
rather than discarded — see finding 3.

Verdicts:

| verdict | meaning |
|---|---|
| `agree` | the same single edge is the front on both sides |
| `futurelot_extra_front` | FutureLot calls our front a front *and* calls another street edge a front too |
| `engine_extra_front` | the reverse — our `all_fronts` rule marks a second front FutureLot does not |
| `different_front` | FutureLot's front is an edge we did not call front |
| `no_front` | one side produced no front edge |

```bash
python3 compare.py
```

## Files

| Path | What it is |
|---|---|
| `FINDINGS.md` | What the run actually found — read this first |
| `seeds.json` | Seed queries per jurisdiction, tried in order (residential intersections first) |
| `qa_common.py` | Path bootstrap, geocode cache, geometry helpers, the labeling call |
| `county_overrides.py` | QA-local parcel-layer substitutions (see finding 5) |
| `unpack_probe.py` | Restores the browser probe's packed form |
| `data/futurelot_packed.json` | The probe's raw packed output, as read from the browser |
| `data/candidates.json` | Every corner lot found per jurisdiction, ranked |
| `data/selected.json` | The one lot per jurisdiction the rest of the harness uses |
| `data/engine_results.json` | Full labeling output per lot |
| `data/futurelot_observations.json` | FutureLot's lot edges per lot |
| `data/comparison.json` | The merged record behind the report |
| `out/report.md`, `out/report.csv` | The readable results |
| `out/discovery.log` | Phase A transcript — which seeds worked, what was rejected |

## Re-running

Phases are independently re-runnable and write incrementally, so a single
jurisdiction can be redone without disturbing the rest:

```bash
python3 find_corner_lots.py --jurisdiction "Mill Valley"
python3 run_engine.py --jurisdiction "Mill Valley"
```

Geocodes are cached in `data/geocode_cache.json`; a re-run spends no Google
quota on seeds it has already resolved.
