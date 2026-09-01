# Front-edge QA — findings

One corner lot per jurisdiction, 28 of 28. Engine labels from the production
path (Google geocode → county fabric → jurisdiction front rule → Google Roads
namer), FutureLot's labels from its own report route. Generated data is in
`data/`, the full table in `out/report.md`.

**Run date: 2026-09-01.**

## Cross-checks first

Nothing below is a labeling difference until the two sides are provably
describing the same parcel:

| Check | Result |
|---|---|
| APN agreement (ours vs FutureLot `parcel_id`) | **28 / 28** |
| Lot centroid within 60 ft | **28 / 28** |
| Lot area within 15% | **27 / 28** (Fairfax off by 1.26×) |
| Every significant FutureLot edge matched to one of ours | **22 / 28** |

So the disagreements below are real disagreements, not two systems looking at
different lots.

## Headline

| Verdict | Count |
|---|---|
| `futurelot_extra_front` — FutureLot calls our front a front *and* calls another street frontage a front too | **19** |
| `agree` — same single frontage is the front on both sides | **5** |
| `different_front` — FutureLot's front is an edge we did not call front | **3** |
| `no_front` — FutureLot produced no front lot line at all | **1** |

## 1. FutureLot treats nearly every corner lot as dual-front (19/28)

On 19 of 28 lots FutureLot labels **both** street frontages `front`. We label
one `front` and the other `street_side`.

This is not a geometry disagreement — on all 19 it agrees with us about which
edge our front is, and adds a second. It reads as a jurisdiction-independent
policy: a conservative "both frontages are front" default, applied regardless
of the local rule. It appears under every rule in our database:

| Our rule | `futurelot_extra_front` | `agree` |
|---|---|---|
| shortest_frontage | 7 | 3 |
| owner_elected | 5 | 1 |
| designated | 3 | 0 |
| all_fronts | 2 | 1 |
| address_street | 2 | 0 |

The consequence is a setback consequence, which is the point of the exercise:
a second front carries the front setback, not the street-side setback. On
**Palo Alto 589 Coleridge Ave** (rule `owner_elected`, PAMC 18.09.040(j)(4) —
16 ft front / 10 ft street side, owner's election) FutureLot marks both
Coleridge and Webster as front and its detached-ADU front setback comes back as
the "not permitted in front yard" sentinel (`front_val: 1000000`). Under the
cited election the owner may put the front on Coleridge and take the 10 ft
street-side on Webster.

Where our own database says `all_fronts` (Hillsborough, Sunnyvale) we and
FutureLot converge — as expected, since that is the rule FutureLot appears to
apply everywhere.

**This is the finding to take to counsel**: our per-jurisdiction rules and
FutureLot's uniform dual-front reading disagree on 19 of 28 corner lots, and
the difference is worth 6 ft of setback on a typical lot.

## 2. Three genuine front disagreements

### 2a. San Mateo County (unincorporated) — 843 6th Ave — *our rule, their address*

| | front | frontages |
|---|---|---|
| engine | **Bay Rd** (55.9 ft) | Bay Rd + 6th Ave |
| FutureLot | **6th Ave** (98.5 ft) | calls Bay Rd `side` |

The rule is `shortest_frontage`, so the shorter Bay Rd face is the front. The
situs address is *843 6th Ave*, and FutureLot follows the address street.
This is exactly the divergence the jurisdiction database exists to produce —
address-street matching alone is legally correct in 1 of 28 jurisdictions —
and here our answer follows the cited code and theirs does not.

### 2b. Los Altos — 58 Lyell St — *our parcel geometry is wrong*

Same APN (17039026), same centroid (4 ft), similar area — **different shape**:

* FutureLot: a clean 50 × 142 ft rectangle (4 edges, axis-aligned).
* Our engine: a **triangle** — 3 edges, 141 ft / 118 ft / 123 ft at bearings
  0° / 36° / 146°.

The Santa Clara county fabric polygon for this parcel does not agree with
FutureLot's source. Everything downstream of it — front, rear, setback
envelope — is computed on the wrong outline. On the same lot the Roads namer
also returned `unnamed rd` for one frontage.

*Action: check the Santa Clara fabric against another source for this APN; if
the fabric is bad here it will be bad elsewhere, and nothing in the pipeline
currently notices.*

### 2c. Napa County (unincorporated) — 481 Newton Way — *our Roads namer*

Downstream of finding 3 below. See there.

## 3. Our defect: the Google Roads namer merges two frontages into one (3/28)

On three lots the Roads namer returns **one street name for both frontages**,
so the engine merges them into a single frontage, the lot stops being a corner,
and the front lands on the wrong street. Census (neighbour-address) naming gets
these right on the same fetch:

| Lot | census naming | Roads naming | resulting front |
|---|---|---|---|
| **845 Coventry Rd, Kensington** | Coventry Rd (88 ft) + Ardmore Path (150 ft) | one 238 ft `ardmore path` | **Ardmore Path** — the lot's own address is *Coventry Rd* |
| **481 Newton Way, Angwin** | Toyon St (65 ft) + Newton Way (75 ft) | one 140 ft `toyon st` | **Toyon St** — address is *Newton Way* |
| **329 Ethel Ave, Mill Valley** | 3 street sections | one 185 ft `ethel ave` | corner collapses to single frontage |

That is **11% of corner lots**, and the failure is silent: the result is a
confident `single_frontage` / high-confidence front on a lot that has two
streets. It bears directly on the merge decision recorded in
`gaudi-api-port/HANDOFF.md` — Roads adopted as a higher-precedence naming
oracle over the census fallback. Roads is more accurate when it is right and
catastrophic when it snaps both frontage-section midpoints to the same road.

*Suggested guard: when Roads returns a single name for frontage sections whose
bearings differ by more than ~45°, distrust it and fall back to census for that
lot (or keep the sections split and flag). The engine already has the census
answer in hand — it computed it.*

The QA harness records both labelings per lot (`analysis` vs `analysis_census`)
and flags the divergence as `roads_collapsed_frontage`, so this is measurable
on any future run.

## 4. FutureLot produced no front at all (1/28)

**Mill Valley — 329 Ethel Ave**: every one of FutureLot's five edges is
labelled `side`. No front, no rear. A lot with no front lot line cannot have a
front setback applied, so this is a defect on their side (ours has the Roads
collapse on the same lot, so neither system handles it).

## 5. Provider gap: unincorporated Sonoma County has no parcel coverage

The Sonoma entry in `services/parcel_data/county_registry.py` points at
`OWTSPublic/Cities_GIS_Parcel_Base` — which, as the name says, carries the
county's *cities*. Point queries in unincorporated territory return zero
parcels:

```
Boyes Hot Springs  0 parcels    Penngrove  0 parcels
Guerneville        0 parcels    Graton     0 parcels
```

So the provider cannot serve any address in unincorporated Sonoma County, and
that jurisdiction's `owner_elected` front rule is unreachable end-to-end. The
county also publishes `OneStopMapPublic/One_Stop_Parcels`, which is countywide
and carries APN, situs, jurisdiction and zoning columns (verified: a point
query in Guerneville returns APN 070-050-018, 16129 Main St).

*Action: swap the registry's Sonoma layer for `One_Stop_Parcels`, or add it as
a fallback.* The QA runs Sonoma under a local substitution
(`county_overrides.py`) so the rule could be tested at all; the lot it found,
365 Calle del Monte, behaves normally.

## 6. Smaller notes

* **Fairfax 73 Scenic Rd** — our lot area is 1.26× FutureLot's. Worth a look;
  every other lot agrees within 3%.
* **Rear/side assignment differs widely even when the front agrees.** "Rear" is
  defined relative to the front, so once FutureLot adds a second front its rear
  moves. On Palo Alto their `rear` is our `side` and their `side` is our `rear`,
  with all four edges matching geometrically at 0 ft offset.
* **FutureLot encodes "not permitted" as a sentinel distance**, not a flag:
  `front_val` of `1000000` (Palo Alto, Menlo Park, Los Altos) or `2000000`
  (San Mateo County unincorporated) rather than a null. Anything consuming that
  field numerically would site a building a hundred miles back.

## Harness defects found and fixed along the way

Recorded because they would have produced a wrong QA rather than a wrong answer:

1. **Discovery's neighbour window did not match the provider's.** Taking the 12
   nearest centroids from a wide fabric drops abutters whose centroid is far,
   leaving their shared edge looking like a street. Six of 28 lots stopped
   being corners when the production path re-labelled them. Discovery now
   mirrors `fetch_parcel_context` exactly (`_neighbors_like_production`).
2. **Discovery's fabric can truncate.** One 200-record envelope in a dense grid
   can cut off an abutter, so a lot can look like a corner in discovery and not
   be one under the provider's own fetch. Phase B now falls through the ranked
   candidates until a lot is a corner on the production path.
3. **The residential filter was too literal.** The statewide zoning layer's
   description is often just the code again (`R-6`, `3-DUA`, `RL-20`), so a
   search for the word "residential" silently eliminated whole counties. It now
   rejects only on a positive non-residential signal.
