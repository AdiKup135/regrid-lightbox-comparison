# Building-footprint sources for the ADU setback engine

Surveyed 2026-10-18. Every "verified" entry was hit with a live `/query` (ArcGIS), a DuckDB read of S3 GeoParquet (Overture) or a HEAD/manifest download (Microsoft) from this machine; counts are what came back for a ~100 m bbox around the test point. Full records, exact URLs and quirks are in `building_footprint_sources.json`.

## Jurisdiction → best source

| Jurisdiction | County | Best source (layer) | Coverage / vintage | Attributes worth having | Verified |
|---|---|---|---|---|---|
| Atherton | San Mateo | SMC `Building_Footprints/0` (AGOL yq3FgOI44hYHAFVZ) | countywide; LiDAR (likely 2020), edited daily, 229k polys | BLDGHEIGHT | yes – 200, 40 feats @Atherton |
| Hillsborough | San Mateo | SMC `Building_Footprints/0` | same | same | yes (county) |
| Menlo Park | San Mateo | SMC `Building_Footprints/0`; city `GISWeb/Buildings/MapServer/3` for tags | city: 2015 ortho + 2020 county LiDAR, rev 2024 | city: Address, Stories, BldgSubType (Garage/Carport) | yes – city 200, 27 feats |
| Portola Valley | San Mateo | SMC `Building_Footprints/0` | same | same | yes (county) |
| San Carlos | San Mateo | SMC `Building_Footprints/0` | same | same | yes (county) |
| San Mateo (city) | San Mateo | SMC `Building_Footprints/0` (city copy `Building_Footprints_Zoning/26` is 2023 + zoning) | county daily / city 2023 | city: ZONECLASS | yes – city 200, 27 feats |
| SMC unincorporated | San Mateo | SMC `Building_Footprints/0` | same | same | yes (county) |
| Los Altos | Santa Clara | SCC `basic/SCCBuildings/MapServer/0` (2022 LiDAR); city `Building_2022LiDAR_Footprints/0` identical | late-2022 Sanborn LiDAR | Building_H | yes – city 200, 35 feats |
| Los Altos Hills | Santa Clara | SCC `SCCBuildings/0` | 2022 LiDAR | Building_H | yes (county) |
| Mountain View | Santa Clara | SCC `SCCBuildings/0` (city `Public/BuildingFootprint` host unreachable) | 2022 LiDAR | Building_H | county yes; city **no** (connect refused) |
| Palo Alto | Santa Clara | SCC `SCCBuildings/0` geometry + city `BuildingRoofOutLine/0` for major/minor | county 2022 LiDAR; city roof outlines 1999–2013 photos, edited 2026-08 | city: BUILDINGCLASS major/minor | yes – county 200, 22; city 200, 27 @Palo Alto |
| San Jose | Santa Clara | SCC `SCCBuildings/0` (city `OPN_OpenDataService/187` host unreachable) | 2022 LiDAR | Building_H | county yes; city **no** (connect refused) |
| Saratoga | Santa Clara | SCC `SCCBuildings/0`; city `Building/FeatureServer/14` = 2018 ortho outlines | 2022 LiDAR / 2018 ortho | none in city layer | yes – city 200, 32 feats |
| Sunnyvale | Santa Clara | **City** `Building_Footprints/0` (AGOL IBwZaktrBtZuqQmg) | city, data 2023-08 | APN, Address, BLDG_TYPE Main/Accessory(<100/100-700/>700), STORY, BLDG_HEIGH | yes – 200, 12 feats |
| SCC unincorporated | Santa Clara | SCC `SCCBuildings/0` | 2022 LiDAR | Building_H | yes (county) |
| Fairfax | Marin | Marin `Building_Footprints/0` (AGOL T8eS7sop5hLmgRRH) | 2004 stereo base + 2014/2018 adds + town plans; edited 2023-02 | BuildingType (use), SourceDateYear | yes – 200, 68 feats @Mill Valley |
| Mill Valley | Marin | Marin `Building_Footprints/0` | same | same | yes |
| Sausalito | Marin | Marin `Building_Footprints/0` | same | same | yes (county) |
| Marin unincorporated | Marin | Marin `Building_Footprints/0` | same | same | yes (county) |
| Lafayette | Contra Costa | **Overture buildings 2026-09-23.0** (no county/city layer) | MS ML geometry via Overture, heights from 3DEP | height | yes – 11 feats @Lafayette via DuckDB/S3 |
| Moraga | Contra Costa | Overture buildings | same | height | (same source) |
| Orinda | Contra Costa | Overture buildings | same | height | (same source) |
| CCC unincorporated | Contra Costa | Overture buildings | same | height | (same source) |
| Healdsburg | Sonoma | Sonoma `BASEPublic/Buildings/FeatureServer/0` (socogis) | 2000 base, updated to May-2025 EagleView ortho; ≥150 sf only | PropType (Single Family Residence / Out Building …) | yes – 200, 33 feats @Healdsburg |
| Windsor | Sonoma | Sonoma `BASEPublic/Buildings/0` | same | same | yes (county) |
| Sonoma unincorporated | Sonoma | Sonoma `BASEPublic/Buildings/0` | same | same | yes (county) |
| Napa (city) | Napa | Napa `BuildingFootprint_Public/0` (AGOL Ko5rxt00spOfjMqj, PDDL) | maintained, weekly sync (2026-10-16) | FEATURECODE Addressed Building / Outbuilding…, Parcel (APN), Address, Municipality | yes – 200, 14 feats @Napa |
| Napa unincorporated | Napa | Napa `BuildingFootprint_Public/0` | same | same | yes (county) |

"yes (county)" = the county layer was verified at one test point in that county; the jurisdiction itself was not separately probed.

## Global baselines (verified)

| Source | What was verified | Vintage / license | Merges house + garage? |
|---|---|---|---|
| **Overture Maps buildings** `s3://overturemaps-us-west-2/release/2026-09-23.0/theme=buildings/type=building/` | DuckDB anonymous S3 read: Atherton 29 features (all OSM-sourced, 24 with height, 2 with class), Lafayette 11 features (all "Microsoft ML Buildings", 11 with height, 0 with class). ~185 s per bbox straight from S3. CLI: `overturemaps download --bbox=-122.1988,37.4603,-122.1968,37.4623 -f geojson --type=building -o out.geojson` | monthly releases; theme is ODbL (OSM) with CDLA/CC-BY inputs; attribution "© OpenStreetMap contributors" | OSM-sourced: house + *attached* garage usually one polygon, detached garages separate. MS-sourced: generalized roof blobs, can merge a house with a nearly-touching detached garage/carport, can split under trees. Provenance flips per parcel — read `sources[0].dataset`. |
| **Microsoft GlobalMLBuildingFootprints 2026-08-13** manifest `https://bfppub.blob.core.windows.net/$web/2026-08-13/dataset-links.csv` → tiles `…/RegionName=UnitedStates/quadkey=<L9>/part-*.csv.gz` | Manifest downloaded (30,341 rows, 2,415 US tiles); HEAD 200 on quadkey 023010230 (Atherton + Palo Alto, 91.5 MB). Tiles for the other test points: 023010203 Mill Valley, 023010212 Lafayette, 023010201 Healdsburg, 023010210 Napa. Old host `minedbuildings.blob.core.windows.net` now returns 409. | imagery 2014–2024; CDLA-Permissive-2.0 (README; Planetary Computer labels it ODbL) ; props: height (m, −1 unknown), confidence | Yes, often — pure ML roof segmentation; adjacent roofs merge. |
| Microsoft USBuildingFootprints v2 (legacy) `https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/California.geojson.zip` | HEAD 200, 466 MB, 11.5 M CA polygons | ~2012–2020; ODbL | Yes, same behaviour; frozen — offline fallback only. |

## Recommendation

**Baseline = county layer, fetched by parcel polygon through the existing ArcGIS client** (same keyless `/query` dialect; add a `building_layer_url` + `primary_pick` block per county to `county_registry.py` — a ready-to-paste block is in the JSON under `recommended_registry_extension`). Query with the parcel polygon as `geometry` (esriGeometryPolygon) so one call returns every structure on the lot, clip each to the parcel, then choose the primary house.

Per-county overrides:

- **San Mateo (06081)** – `Building_Footprints/0`. No type/APN flag → primary = largest clipped area. Roof-extent (LiDAR) outlines. Vintage undocumented; flag it.
- **Santa Clara (06085)** – `basic/SCCBuildings/MapServer/0` (2022 LiDAR, Building_H). Roof-extent. Override **Sunnyvale** with the city layer (APN + `BLDG_TYPE='Main'`); for **Palo Alto** use county geometry and the city roof layer's `BUILDINGCLASS='major'` only to pick the main building. San Jose / Mountain View city hosts are unreachable from a non-local network — county layer covers them.
- **Marin (06041)** – `Building_Footprints/0`. Stereo-compiled wall outlines (good for setbacks) but 2004-era base; use `SourceDateYear` and fall back to Overture when the house looks newer than the footprint (e.g. footprint area ≪ assessor improvement). `BuildingType` is a use code, not main/accessory.
- **Contra Costa (06013)** – **gap**: no county or city (Lafayette/Moraga/Orinda) layer exists. Use Overture; pre-extract the six-county bbox once per release into local GeoParquet/PostGIS — the S3 scan is far too slow (~3 min) for request time. Microsoft tile 023010212 is the direct alternative.
- **Sonoma (06097)** – `BASEPublic/Buildings/0` (same host as the parcel fabric). `PropType='Single Family Residence'` picks the house, `'Out Building'` the accessories; null PropType → area heuristic. Structures <150 sf absent.
- **Napa (06055)** – `BuildingFootprint_Public/0` (PDDL, weekly). `FEATURECODE` startswith `Addressed Building` = house; `Outbuild*` / `Non-Address*` = accessory (values have typos). `Parcel` holds comma-separated APNs — split before matching.

Main-house heuristic where no flag exists: among polygons intersecting the parcel, drop those with <120 sf clipped area, prefer the one containing the situs/address point, else the largest clipped area. Record `outline_kind` per source: LiDAR layers (SMC, SCC, Los Altos, City of San Mateo) and Palo Alto's roof layer are **roof** extents — expect ~1–2.5 ft over-statement at eaves relative to wall-measured setbacks; Marin (stereo), Sonoma/Napa (ortho-digitized) are closer to wall lines.

## Known gaps and caveats

1. **Contra Costa County has no open footprint layer** (county server enumerated, AGOL catalog searched, 3 cities searched: nothing). Overture/Microsoft only — ML geometry, no main/accessory flag, merged roofs possible.
2. **San Jose and Mountain View city services refused connections** from two network paths (`geo.sanjoseca.gov`, `maps.mountainview.gov`); endpoints are recorded but unverified. The county 2022 LiDAR layer covers both.
3. **San Mateo County layer vintage is undocumented** (empty description, `LASTUPDATE`/`FLOORCOUNT`/`FEATURECODE` all null); it is probably the 2020 LiDAR product plus edits. The frozen 2022 sibling `Buildings/FeatureServer/0` has APN + `OutBuild` + `BUILD_TYPE` if a one-time main/accessory lookup is needed.
4. **Marin is 2004-based** with partial 2014/2018 updates — the weakest county source for current house outlines.
5. **Santa Clara 2022 vs 2020 layers disagree** (22 vs 29 features in the same Palo Alto bbox); small detached structures may be missing from the 2022 product — cross-check `SCCGISHUB/MapServer/40` when a garage is expected but absent.
6. **No small-town layers** exist for Atherton, Hillsborough, Portola Valley, San Carlos, Los Altos Hills, Fairfax, Mill Valley, Sausalito, Lafayette, Moraga, Orinda, Healdsburg, Windsor (AGOL catalog, 2026-10-18).
7. **Licensing**: only Napa states a license (PDDL). SMC/SCC/Marin/Sonoma are county open-data "as is"; city layers (Sunnyvale via a consultant account, City of San Mateo via a staff account) carry no license text and could disappear — keep the county layer as the fallback for each.
8. **Overture/Microsoft at request time**: not viable straight from S3/blob; cache a six-county extract and refresh monthly (Overture) / per drop (Microsoft).
