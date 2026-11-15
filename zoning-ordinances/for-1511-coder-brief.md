# Brief for the agent implementing FOR-1511 — [Zoning]: [Setbacks]: local 0 front setback for state track

Attached to the Linear ticket. Paste everything below the line into a fresh Claude Code session opened on the site repo (`/Users/adi/Documents/formX/site`). Written 2026-10-18.

---

## Background

FormX builds an ADU setback engine (Python 3.12 / Flask / Shapely). The Phase A prototype lives in this repo under `gaudi-api-port/` (the production home is the separate `repos/Gaudi` gaudi-api; do NOT touch it). The engine evaluates one detached, new-construction ADU on a single-family lot. Two tracks: the **state track** (Gov. Code §66323(a)(2): unit ≤ 800 sf and ≤ 16 ft, or 18 ft inside a CA HQ Transit Area → 4 ft side/rear; front = the local jurisdiction's zoning-district front setback for the SFR zone, city or county, per counsel 2026-09-24) and the **local track** (§66314, not in scope here).

Per-jurisdiction data for 28 Bay Area jurisdictions lives in `zoning-ordinances/zoning_ordinance_links.json` (field `residential_front_setback` with `value_ft`, `citation`, `by_district` keyed on the parcel's zone code; `front_rule` with `address_street | shortest_frontage | designated | owner_elected | all_fronts`).

Decision (Adi, 2026-10-18): the engine must describe what a lot has **by right**. Where a local ADU chapter itself sets a front rule for the ≤ 800 sf unit, the state track must take **that value** (it is 0 ft, "no front setback", in all six such chapters today, but the engine reads the number and never assumes 0), because a city may always be more lenient than state law. Scope of this ticket (Adi, 2026-10-18): only those six `grant_local` chapters go on the local path; every other reading (mixed, silent, conditional, lot-specific) stays on the jurisdiction's zoning front, with the flag the data block carries. Where the chapter only says the district front "yields if it would preclude an 800 sf unit", that is a case-by-case concession at the counter, so the district front stays. A full read of all 28 chapters was done on 2026-10-18 and folded into `zoning-ordinances/zoning_ordinance_links.json` as the `state_track_front` block of each jurisdiction record (rule, value_ft, value_rule, flags, classification, threshold_sf, verbatim quote, citation, placement_rule, notes). There is no separate research file.

Repo policy: flat, main-only, no branches or worktrees; do not commit or push unless Adi asks. Style: Python, small functions, flags as snake_case strings, every value carries a citation / basis string. Existing tests: 141, pytest, must stay green.

## Task

Implement Linear ticket **FOR-1511 "[Zoning]: [Setbacks]: local 0 front setback for state track"**. If the Linear MCP is available, read the ticket first; it holds the overview, the per-chapter table, acceptance criteria and open questions. Do not edit its description (you may add a comment with your results at the end). Everything below restates what you need in case Linear is unavailable.

### What to build

A new branch in the state-track front resolution, right after the track decision and before the front value is resolved: **"Does the local ADU chapter set its own front rule for the ≤ 800 sf unit?"**

- yes → front = **whatever value the local exception sets** (read `value_ft` from the data; it is 0 ft in all six today, but the engine must never assume 0), basis = the local citation + verbatim quote, flag `front_from_local_adu_chapter`
- no → today's behaviour (district front from `residential_front_setback` / `by_district`, or `front_setback_missing`), unchanged.

Source of the per-jurisdiction answer: the `state_track_front` block in `zoning-ordinances/zoning_ordinance_links.json` (28 records; `rule` ∈ `local | district`, `value_ft`, `value_rule`, `flags`, `classification` ∈ `grant_local | conditional_yield | district_applies | silent | mixed`, quote, citation, `threshold_sf`, `placement_rule`, notes). The `rule`, `value_ft` and `flags` fields already encode the mapping below; the table is for your understanding and for the tests. Terminology: "district value" below always means the **local jurisdiction's** (city, or county for unincorporated land) zoning-district front setback for the SFR zone, i.e. today's `residential_front_setback` / `by_district` lookup. It never means "county".

Mapping to engine behaviour:

| classification | jurisdictions | engine |
|---|---|---|
| grant_local | Atherton, Marin County, Napa, Portola Valley, San Mateo, Sunnyvale | **the only six on the local path in this ticket**: local `value_ft` (0 ft in all six) + `front_from_local_adu_chapter`. Napa grants by disapplication (its front-setback subsection "does not apply to" §66323(a) units) → also flag `front_local_grant_by_disapplication` |
| mixed | Healdsburg | district value + `front_rule_mixed` (its Table 20a note exempts ADUs ≤ 800 sf unconditionally, but Adi scoped this ticket to grant_local only; stays on the zoning front until counsel reads it) |
| mixed | San Carlos | district value + `front_rule_mixed` |
| conditional_yield (9), district_applies (Santa Clara County) | | district value, no new flag |
| silent (10) | Contra Costa County, Fairfax, Hillsborough, Lafayette, Menlo Park, Mill Valley, Orinda, Palo Alto, San Jose, Sausalito | district value + `front_rule_silent` (pending counsel) |
| conditional_yield, but with an ADU-specific NON-ZERO rule | San Mateo County (8.392.050(4)(a): front = the lesser of the district front or the primary residence's own distance from the front lot line, for every ADU) | out of scope for this ticket: `rule: district` + flag `front_rule_needs_primary_footprint` (the block keeps `value_rule` for the later footprint work; do not silently use the district value without the flag) |

- Los Altos Hills (40 ft ADU-specific) and Santa Clara County ("same front as the primary residence") set ADU-specific fronts equal to the district value: leave them on the district path, no new flag.
- all_fronts jurisdictions (Hillsborough, Sunnyvale, Contra Costa County): the address-street front follows this branch; the second frontage stays at the state 4 ft as today.
- A manual `front_setback_ft` override in the request body still wins over everything (existing `FLAG_FRONT_SETBACK_MANUAL` behaviour).
- Local track (Phase B) is untouched.

### Where

- `gaudi-api-port/services/compute/adu_setbacks/state_track.py`: `state_track_setbacks()`, `FrontSetback`, `CITE_FRONT`, `FLAG_FRONT_*` — add the rule and the new flags / basis strings here.
- `gaudi-api-port/services/compute/adu_setbacks/evaluate.py` and `routes/adu_setbacks.py` (`POST /adu/evaluate`): wherever the `FrontSetback` is built from the jurisdiction record, read the new field.
- Data: the per-jurisdiction `state_track_front` block already exists in every record of `zoning-ordinances/zoning_ordinance_links.json` (folded 2026-10-18; the file's top-level `_schema` block documents every field — read it first, and if you change the data schema in any way, update `_schema` and add a changelog line, per Adi). Nothing to generate: wire the engine to it. Keep `residential_front_setback` as is and do not edit the blocks.
- Debug UI in this repo (the EdgesPanel / zoning-summary panel that shows per-edge values and the basis text): show the local value with the explanation "<City>'s ADU ordinance sets the front setback for this unit to <value> (<citation>)" (reads "no front setback" when the value is 0) and surface the new flags. Do not touch `repos/Gaudi`.

### Comment convention (required)

Every block you change or add, in every file, carries the comment line exactly:

```
# 1.5.1  FOR-1511 [Zoning]: [Setbacks]: local 0 front setback for state track
```

Use `//` or `<!-- … -->` with the same text in JS / HTML. JSON has no comments, so the `source` string above carries the ticket id. This is how Adi tracks the change.

### Acceptance criteria

1. **Unit tests.** Existing suite green. New tests cover every classification value, Napa's extra flag, Healdsburg and San Carlos (both district + `front_rule_mixed`), an all_fronts jurisdiction (Sunnyvale: address street 0 ft, second frontage 4 ft), the manual override winning, a synthetic record with `rule: local, value_ft: 10` (front must come out 10 ft — the engine reads the value, it never assumes 0), San Mateo County (district value + `front_rule_needs_primary_footprint`), and a jurisdiction with no `state_track_front` field (falls back to today's behaviour and the `front_setback_missing` logic).
2. **End-to-end verification with real addresses.** Find one real single-family address per row of the table: grant_local (Atherton — the "Webster" lot Adi used if you can find it, else any; Marin County **unincorporated**, e.g. Kentfield / Greenbrae / Strawberry, not a city; Napa city; Portola Valley; San Mateo city; Sunnyvale), mixed (Healdsburg, San Carlos), conditional (Windsor or Saratoga), district_applies (Santa Clara County unincorporated), silent (Fairfax, Palo Alto). Run each through the running API (start it the way the repo documents: README, `.claude/launch.json`, the Flask entry point; geocoding uses the Google key if configured in the environment, otherwise the free fallback geocoders already wired in `services/parcel_data`; do not sign up for anything). Confirm the geocoder put each address in the intended jurisdiction and zone, then record expected vs actual front value, basis text and flags in `zoning-ordinances/for-1511-verification.md` (a table plus how to rerun). Use parcel addresses only; never record owner names. If an address cannot be resolved, say so and pick another.
3. **Report.** The diff summary, pytest output, the verification table, and anything you could not verify. Then, if the Linear MCP is available, add a comment on FOR-1511 with the verification table.

### Do not touch

`zoning-ordinances/adu-setback-decision-tree.html`, `zoning-ordinances/diagrams-backup/`, `adu-local-track-trees.html`, `local_track_trees_template.html`, `make_local_track_trees.py`, `adu_local_track_model.json`, `adu_over800_survey.json`, `building_footprint_sources.*`, and the `state_track_front` blocks inside `zoning_ordinance_links.json` (read-only input; the engine code you add may read them, never rewrite them). Do not commit or push; leave the working tree for Adi to review.
