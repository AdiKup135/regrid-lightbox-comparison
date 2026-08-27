# Audit: `front_rule.rule == "all_fronts"`

**Date:** 2026-08-27
**Scope:** the 4 jurisdictions in `zoning_ordinance_links.json` labeled `all_fronts`.
**Status:** applied. Fairfax and San Jose reclassified; San Jose's two overrides encoded. See [Actions applied](#actions-applied).

`front_rule_note` in the data file defines `rule` as *"how the jurisdiction declares the FRONT of a multi-street lot."*
That definition is the yardstick used throughout this audit. It matters, because a rule that assigns
**setback distances** to every street frontage is not the same as a rule that **declares every street
line to be a front** — and two of the four entries conflate the two.

## Summary

| Jurisdiction | Current | Verdict | Correct value |
|---|---|---|---|
| Sunnyvale | `all_fronts` | ✅ Correct | `all_fronts` |
| Hillsborough | `all_fronts` | ✅ Correct | `all_fronts` |
| Fairfax | `all_fronts` | ❌ Misclassified | `shortest_frontage` |
| San Jose | `all_fronts` | ❌ Misclassified | `shortest_frontage` + 2 conditional overrides |

This took `all_fronts` from 4 → 2. Repo-wide distribution is now:
`shortest_frontage` ×11, `owner_elected` ×5, `designated` ×4, `all_fronts` ×2, `address_street` ×1.

---

## Sunnyvale — correct

`all_fronts` holds. The definitional anchor is **SMC 19.12.260(1)(a)**, which defines the front yard as one

> …paralleling **the street or streets** upon which the lot abuts…

The plural is the whole basis for the classification: every abutting street line is a front. There is no
election and no address-street test.

Which front is *primary* comes from three further places:

| Section | Establishes |
|---|---|
| 19.12.260(1)(b) | Rear yard sits opposite the **narrower** frontage → short frontage is the primary front |
| 19.12.130(18) | Lot width is measured at the "required front yard," defined as the one **not** reducible under 19.34.040 |
| 19.34.040(b) | Front yard on the **longer** street frontage is reducible to **9 ft** in R-0/R-1/R-1.5 (and duplex/SFR in R-2) where streets intersect at ≥60° |
| Table 19.79.070 | Carries a dedicated "Reducible front (longer street frontage of corner lots)" row for ADUs |

So Sunnyvale is all-fronts, but *asymmetric*: short frontage is the hard front (~20 ft), long frontage is
the soft front (9 ft). Table 19.79.070 also shows front setback = n/a for new-construction ADUs, consistent
with the ≤800 sf soft-front rule.

**Action taken:** citation rewritten in commit `da99930`. `rule` was already correct and is unchanged.

---

## Hillsborough — correct

`all_fronts` holds, and it is the strongest case of the four — because Hillsborough has **no front concept at all**.

**HMC 17.24.020(A):**

> The street-line setback area is that twenty-five foot wide strip of land that is bounded on one side by
> the street line… **If the lot is bounded by more than one street line, the area bounded by all street
> lines and their parallel lines twenty-five feet distant constitutes the street-line setback areas of the lot.**

The code is a strict binary — street line vs. not-street-line — with no front/side/rear anywhere:

- **17.24.020(A)** — every street line: 25 ft, uniform.
- **17.24.020(C)** — interior setback (any lot line that is *not* a street line): 20 ft. Overlaps between
  the two resolve **to the street-line setback**.
- **17.24.020(B)** — where the ROW is an easement rather than dedicated fee, the outer boundary is the
  easement line; where established by public use, it is the edge of pavement.
- **17.24.020(D)** — no dwelling closer than 50 ft from the centerline of any ROW, capped at 30 ft from the street line.
- **17.24.020(F)** — single-family residences ≥8,000 sf: setbacks increased 15 ft in aggregate, minimum 5 ft added to the street-line setback.

**Corroborating negative evidence** — the definitions chapter (17.08) contains:

- **zero** occurrences of the word "corner"
- no "front lot line," no "front yard" (only 17.08.090 *Frontage*, which defers to § 1.04.010)
- 17.08.140 *Lot line*: "the established division line between lots" — undifferentiated

There is no front to declare, so every street line is treated alike by construction.

**Existing citation** (`HMC 17.24.020(A) - 25 ft street-line setback on every street frontage; no front concept`)
is accurate. It could optionally be strengthened with the 17.08 negative evidence and the (D)/(F) modifiers.

---

## Fairfax — misclassified

**Current citation:** `TC 17.040.020(D) - 10 ft on every street frontage of a corner lot`

That section is real and quoted correctly:

> **§ 17.040.020(D)** All corner lots: all street frontage of any corner lot shall have a yard setback of ten feet.

But it is a **setback** rule, not a front declaration. Fairfax declares its front explicitly and separately,
in a chapter added by **Ord. 885, passed 11-1-2023** — which post-dates the reasoning behind the current label:

> **§ 17.010.110 DETERMINING LOT FRONTAGE**
> (A) The front of a lot that is not a corner lot or through lot is the lot line along the street frontage.
> **(B) The front of a corner lot is the narrowest dimension of the lot with street frontage.**
> (C) …the front yard of a through lot is the one that abuts the street that adjoining lots use to provide primary access…
> (D) In the case of a through lot, the narrowest dimension is the front yard (that is not a panhandle). If same dimension, staff shall determine the front yard.
> (E) If a panhandle lot, then the front yard is the one adjoining the widest portion of the lot that faces the street.

By the schema's own definition of `rule`, that is **`shortest_frontage`**.

Corroborating:

- **§ 17.010.120(B)** refers to a "**corner side yard**" — a concept that only exists if a corner lot has
  one front and one street side.
- **Ch. 17.008 definitions** — *CORNER LOT*: "A lot in the junction of and fronting on two or more
  intersecting streets" (prior code § 17.04.093). The "fronting on two or more" phrasing is what likely
  drove the original `all_fronts` label, but it is a locational description, not an operative front declaration.
- *FRONT YARD* (§ 17.04.615): "A yard extending along the full-length of the **front lot line** between the
  side lot lines" — presupposes a single front lot line. Note Ch. 17.008 never defines *front lot line*;
  *LOT LINE* (§ 17.04.342) is just "The lines bounding a lot." 17.010.110(B) is what fills that gap.

### Practical impact: none

Fairfax's front yard setback is **also 10 ft** (§ 17.040.020(A)), and corner street frontages are 10 ft
under (D). Whichever line is called the front, every street frontage yields 10 ft. **This is a labeling
correctness issue, not an output bug.** The 10-ft-on-all-frontages fact belongs in `street_side_treatment`,
not in `front_rule`.

### Caveat

§ 17.040.020's preamble reads *"no accessory structure or building, including a swimming pool, any part of
which is more than two feet above finished grade, shall be placed in any yard…"* — ambiguous drafting that
could be parsed as applying only to accessory structures. I did **not** trace whether Fairfax's per-district
chapters set separate primary-dwelling setbacks. Worth resolving before relying on the 10 ft figures for
main buildings. It does not affect the front-declaration finding, which rests on 17.010.110(B).

---

## San Jose — misclassified

**Current citation:** `SJMC 20.30.210(A) - oversized corner lots deemed two front property lines`

The cited text exists and says what the citation claims:

> **§ 20.30.210(A) Setback determination — Corner lot.** **If a lot exceeds the defined dimensions of a
> corner lot** it cannot be considered a corner lot and hence is deemed to have two front property lines
> abutting the street sides, and a single rear property line and one (or more) side property line(s). The
> director of planning will make the final determination…

The problem is the leading conditional. This describes the **exception**. The default is stated outright in
the definitions chapter:

> **§ 20.200.700 Lot line.**
> "Front lot line" is the boundary line of a lot which abuts the closest edge of a public or private right-of-way…
> **"Front lot line of a corner lot" is the narrower lot line abutting a public or private right-of-way**…
> **"Side corner lot line of a corner lot" is the longer of the two boundary lines abutting a public or private right-of-way**…
> "Rear lot line" is the boundary line of a lot which is generally opposite of the front lot line.

So an ordinary San Jose corner lot has **one** front — the narrower frontage — and a "side corner lot line."
Default = **`shortest_frontage`**.

### The two genuine `all_fronts` overrides

**§ 20.200.670(A) — oversized corner lots:**

> A residential corner lot is a lot in a residential district on a corner fronting not more than one hundred
> twenty feet on one street and not more than one hundred twenty feet on another. **If both of the street
> frontages exceed the specified frontage widths, the lot is considered to have two front property lines.**

Same structure for commercial districts at a **150 ft** threshold. Note the trigger requires **both**
frontages to exceed — a lot 130 ft × 90 ft is still an ordinary corner lot with one front.

**§ 20.200.670(B) — pedestrian-oriented districts:**

> Notwithstanding the provisions of Section 20.200.670.A, in a pedestrian oriented zoning district, a
> "corner lot" means a lot having at least two frontages on intersecting streets. Such "corner lot" shall
> have a minimum of **two front lot lines regardless of the dimensions of the lot**.

This one is unconditional within those districts and is **not** referenced by the current citation at all.

Also relevant: **§ 20.30.210(B)** gives the director final say on irregular/>4-sided lots, with a floor of
one front and one rear property line.

### Practical impact: real

Unlike Fairfax, this changes output. Most San Jose residential corner lots are ≤120 ft on at least one
frontage, so the common case is `shortest_frontage`, while the file currently asserts `all_fronts` for all
of them.

---

## Actions applied

1. **Fairfax** — `rule` set to `shortest_frontage`, anchored on **17.010.110(B)**. The
   "10 ft on every street frontage" fact (17.040.020(D)) is retained in the citation as street-side
   treatment, with an explicit note that it is a setback rule and not a front declaration. No
   `street_side_treatment` field was introduced — that remains open. **Zero output change.**
2. **San Jose** — `rule` set to `shortest_frontage`, anchored on **20.200.700**. Both `all_fronts`
   overrides encoded in a new optional `front_rule.overrides` array: `oversized_corner_lot`
   (20.200.670.A; thresholds 120 ft residential / 150 ft commercial; **both** frontages must exceed) and
   `pedestrian_oriented_district` (20.200.670.B; not gated on lot size).
   **Real output change** — consumers must evaluate `overrides` before falling back to `rule`.
3. **Hillsborough** — no change made; none required.
4. **Sunnyvale** — citation already rewritten in `da99930`; `rule` untouched.

### Schema addition

`front_rule.overrides` is new and optional: an ordered list of `{rule, condition, citation, description}`
entries (plus `thresholds_ft` where numeric). Evaluate overrides before falling back to `front_rule.rule`;
absent the field, `front_rule.rule` applies unconditionally. `front_rule_note` in the data file documents this.
**San Jose is currently the only entry using it.**

### ⚠️ Known regression until the engine honors `overrides`

`edge-labeling/edge-labeling.ts` reads the rule as `?.front_rule?.rule ?? 'address_street'`
(see the documented lookup at `edge-labeling.ts:729`). It takes a single `FrontRule` string and has no
concept of `overrides`, so San Jose's two override cases now silently resolve to `shortest_frontage`.

Concretely, in that switch (`edge-labeling.ts:607`) the `all_fronts` branch raises the
`second_front_jurisdiction` global flag; the `shortest_frontage` branch does not. So:

| San Jose lot | Before | After | Correct? |
|---|---|---|---|
| Ordinary corner lot (the common case) | `all_fronts` — wrong | `shortest_frontage` — right | ✅ fixed |
| Oversized (both frontages >120/150 ft) | `all_fronts` — right | `shortest_frontage` — wrong | ❌ regressed |
| Pedestrian-oriented district | `all_fronts` — right | `shortest_frontage` — wrong | ❌ regressed |

Net accuracy improves, because the common case is now correct and the override cases are the minority.
But this is a **real regression for that minority**, and it is not self-announcing —
`second_front_jurisdiction` simply stops being raised for those lots. Wiring `overrides` into
`labelEdges` closes it.

### Still open

- No `street_side_treatment` field exists yet; Fairfax's 10-ft-on-all-frontages and Sunnyvale's
  reducible-long-frontage both currently live as citation prose.
- Fairfax's 17.040.020 preamble ambiguity (accessory structures vs. all buildings) is unresolved.
- The other 19 jurisdictions remain unaudited.

## Verification notes

- All ordinance text above was read from the **Zoneomics code mirrors**
  (`zoneomics.com/code/<city>-CA/chapter_N`). The canonical hosts — eCode360 for Sunnyvale, Municode for
  Hillsborough — sit behind bot protection that blocks automated fetching. The `ordinance_link` values in
  the data file remain canonical and resolve normally in a browser.
- Before acting on any of the above, spot-check the quoted language against the canonical host. Hillsborough
  additionally publishes an official Title 17 PDF at `hillsborough.net/DocumentCenter/View/82/Title-17`,
  which was **not** fetched for this audit.
- Fairfax's 17.010 chapter is recent (Ord. 885, 11-1-2023). Mirrors can lag; confirm currency.
- The remaining 19 jurisdictions (`shortest_frontage` ×9, `owner_elected` ×5, `designated` ×4,
  `address_street` ×1) were **not** audited. Given that 2 of 4 `all_fronts` entries were wrong in the same
  direction — an operative setback rule mistaken for a front declaration — the same failure mode is worth
  checking there.
