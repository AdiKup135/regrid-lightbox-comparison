# LightBox vs Zoneomics – API & Field Comparison
**Property:** 1590 Madrono Ave, Palo Alto, CA 94306

---

## API Endpoints Used

### LightBox — 9 endpoint calls
| # | Endpoint | Data Returned |
|---|---|---|
| 1 | `/v1/parcels/address?text=...` | Parcel search / lookup |
| 2 | `/v1/parcels/us/{parcelId}` | Full parcel record |
| 3 | `/v1/structures/_on/parcel/us/{parcelId}` | Structures list on parcel |
| 4 | `/v1/structures/us/{structureId}` (×2) | Individual structure detail (primary + secondary) |
| 5 | `/v1/nfhls/_on/parcel/us/{parcelId}` | National Flood Hazard Layer |
| 6 | `/v1/zoning/_on/parcel/us/{parcelId}` | Zoning data |
| 7 | `/v1/riskindexes/_on/parcel/us/{parcelId}` | Risk index list on parcel |
| 8 | `/v1/riskindexes/us/{riskId}` | Specific FEMA NRI record |
| 9 | `/v1/wetlands/_on/parcel/...` *(implied, empty result)* | Wetlands |

### Zoneomics — 3 endpoint calls
| # | Endpoint | Data Returned |
|---|---|---|
| 1 | `conditionalControls` | Structured best/worst-case zoning controls |
| 2 | `zoneDetail` | Full zone detail incl. permitted uses & all control standards |
| 3 | `zoneDetailParcels` | Zone detail with associated parcel geometry |

---

## Field-by-Field Comparison: Zoning Overlap

### Fields Present in Both — Consistent Values ✅

| Field | LightBox | Zoneomics |
|---|---|---|
| Zone code | R-1 | R-1 |
| Zone name | Single Family Residential District | Single Family Residential |
| Zone type | Residential | Residential |
| Ordinance URL | https://codelibrary.amlegal.com/...76269 | https://codelibrary.amlegal.com/...76269 |
| Zone guide / purpose | Same text | Same text |
| Max FAR (first 5,000 sq ft) | 0.45 | 0.45 |
| Max FAR (excess of 5,000 sq ft) | 0.30 | 0.30 |
| Max site coverage (multi-story) | 35% | 35 |
| Min rear setback | 20 ft | 20 ft |
| Min interior side setback | 6 ft | 6 ft |
| Min street side setback | 16 ft | 16 ft |
| Max building height (base) | 30 ft | 30 ft |
| Max building height (roof pitch ≥ 12:12) | 33 ft | 33 ft |
| Max building height (flood hazard area) | 33 ft | 33 ft (context 1) |
| Max density | 1 unit | 1 du/acre |

---

### Fields Present in Both — Different Values ⚠️

| Field | LightBox | Zoneomics | Note |
|---|---|---|---|
| Min lot area | `perLot: 6,000 sq ft` | Standard field: `9,999`; non-standard clarifies `6,000` for non-flag lots | LightBox reports 6,000 directly; Zoneomics standard field shows 9,999 with 6,000 in the non-standard detail |
| Flood hazard max height | 33 ft (single context) | 33 ft (context 1) AND 20 ft (context 2) | Zoneomics distinguishes two flood hazard height contexts; LightBox only references one |
| Front setback | Long contextual description (20 ft minimum + average setback rules, block calculations, etc.) | "Contextual" / STF | LightBox has full rule text; Zoneomics defers to contextual without detail |
| Permitted uses | Brief text: "HOUSING - SINGLE UNIT, MULTIPLE UNITS, SENIOR, MOBILE HOME PARK" | Granular lists: 13 as-of-right, 8 conditional, 1 prohibited, plus boolean flags | Zoneomics is significantly more detailed |
| Lot area (parcel record) | 566.56 sqm (assessed) / 600 sqm (calculated) | 718.42 sq.yds (~600 sqm) | Different units; calculated values align (~600 sqm); assessed differs slightly |

---

### Fields Only in Zoneomics — Not in LightBox

| Field | Zoneomics Value |
|---|---|
| min_lot_width_ft | 60 ft |
| minimum_site_depth_ft | 100 ft |
| maximum_house_size_sq_ft | 6,000 sq ft (incl. attached garage or one covered parking space) |
| daylight_plane_ft (side yard) | Initial height 10 ft at interior side lot line, 45° angle |
| daylight_plane_ft (rear yard) | Initial height 16 ft at rear setback line, 60° angle |
| (S) Combining max height | 17 ft, limited to one habitable floor |
| Max coverage – patio/overhang | Additional 5% |
| as_of_right uses (detailed list) | 13 individual permitted uses |
| conditional_uses (detailed list) | 8 individual conditional uses |
| prohibited uses | Safe parking |
| Boolean use flags | single_family_permitted, adu_local_permitted, commercial_uses_permitted, etc. |
| min_side_yard_both_ft | NA |
| min_side_yard_at_least_one_ft | NA |
| minimum_built_to_line | NA |
| zone_sub_type | Single Family |

---

### Fields Only in LightBox — Not in Zoneomics

| Category | Fields |
|---|---|
| Parcel / Assessment | APN, FIPS, assessed value, market value, AVM, improvement %, lot number, block, legal description, pool indicator |
| Ownership | Owner names, ownership status (Trustee), owner-occupied flag |
| Structures | Year built, year renovated, living area, footprint area, stories, height (avg/min/max), ground elevation (avg/min/max) for 2 structures |
| Transaction | Last sale date, price, buyer, seller, document type, title company, price per area, loan info |
| Financing | Last recorded loan: lender, value, recording date, due date |
| Tax | Annual tax amount, tax year, delinquent year |
| Flood Hazard (NFHL) | SFHA flag, flood zone (X), 500-year designation, DFIRM ID, panel ID, effective date |
| Risk Index (FEMA NRI) | Overall score/rating, 18 individual hazard scores incl. earthquake (Very High), EAL, social vulnerability, community resilience, national/state percentiles |
| Wetlands | Wetlands intersect check (empty) |
| Census | Tract, block group |
| Geography | CBSA code, county name, opportunity zone flag |
| Zoning ordinance vintage | Ordinance date (2025-03-10), zoning date (2025-04-21) |

---

## Summary

| | LightBox | Zoneomics |
|---|---|---|
| API endpoints called | 9 | 3 |
| Zoning data | ✅ Present (less granular on uses) | ✅ Present (more granular on uses & controls) |
| Physical structure data | ✅ Yes | ❌ No |
| Ownership & transaction data | ✅ Yes | ❌ No |
| Flood & risk data | ✅ Yes (detailed) | ❌ No |
| Permitted use detail | ⚠️ Summary only | ✅ Full lists + boolean flags |
| Daylight plane rules | ❌ No | ✅ Yes |
| Min lot width / site depth | ❌ No | ✅ Yes |
| Max house size | ❌ No | ✅ Yes |
| Parcel geometry (boundary) | ✅ WKT polygon | ✅ MULTIPOLYGON |

*LightBox provides broader property intelligence (ownership, structures, risk, transactions). Zoneomics provides deeper zoning control granularity (use lists, daylight planes, house size limits, combining district rules).*
