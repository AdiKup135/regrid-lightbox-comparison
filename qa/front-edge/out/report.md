# Front-edge QA: engine vs FutureLot

One corner lot per jurisdiction. "Front" is the edge each system calls the
primary front lot line; edges are matched geometrically before their labels
are compared.

## Verdicts

- **different_front** — 3
- **futurelot_extra_front** — 19
- **agree** — 5
- **no_front** — 1

## Cross-checks

Before the labels are compared at all: are the two sides describing the
same parcel, and the same polygon?

- APN agreement (engine vs FutureLot `parcel_id`): **28 / 28**
- Lot area within 15%: **27 / 28**
- Every FutureLot edge matched to one of ours: **22 / 28**
- Lots where our Roads namer merged two frontages into one: **3**  (our defect, not a FutureLot difference)

## Per jurisdiction

| Jurisdiction | Front rule | Lot | Engine front | Fronts (engine / FL) | FL label on our front | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| Lafayette | designated | 680  GLENSIDE DR, Lafayette, CA | glenside dr | 1 / 2 | front | futurelot_extra_front | — |
| Moraga | designated | 838  CAMINO RICARDO, Moraga, CA | camino ricardo | 1 / 2 | front | futurelot_extra_front | — |
| Orinda | shortest_frontage | 9  NORTHWOOD DR, Orinda, CA | northwood ct | 1 / 2 | front | futurelot_extra_front | — |
| Fairfax | shortest_frontage | 73 SCENIC RD, Fairfax, CA | manor rd | 1 / 3 | front | futurelot_extra_front | area x1.26 |
| Mill Valley | designated | 329 ETHEL AVE, Mill Valley, CA | ethel ave | 1 / 0 | side | no_front | roads collapsed frontage; 2 FL edge(s) unmatched |
| Sausalito | owner_elected | 299 GLEN DR, Sausalito, CA | glen dr | 1 / 1 | front | agree | — |
| Napa | shortest_frontage | 1795 LAUREL ST, Napa, CA | laurel st | 1 / 2 | front | futurelot_extra_front | — |
| Atherton | address_street | 256 PRIOR LN, Atherton, CA | prior ln | 1 / 2 | front | futurelot_extra_front | — |
| Hillsborough | all_fronts | 5 HOMEPLACE CT, Hillsborough, CA | homeplace ct | 2 / 2 | front | agree | — |
| Menlo Park | owner_elected | 385 OAK GROVE AVE, Menlo Park, CA | oak grove ave | 1 / 2 | front | futurelot_extra_front | — |
| Portola Valley | owner_elected | 247 ECHO LN, Portola Valley, CA | echo ln | 1 / 2 | front | futurelot_extra_front | — |
| San Carlos | shortest_frontage | 2000 BIRCH AVE, San Carlos, CA | birch ave | 1 / 2 | front | futurelot_extra_front | — |
| San Mateo | owner_elected | 550 BARNESON AVE, San Mateo, CA | barneson ave | 1 / 2 | front | futurelot_extra_front | — |
| San Mateo County (unincorporated) | shortest_frontage | 843 6TH AVE, REDWOOD CITY, CA | bay rd | 1 / 1 | side | different_front | — |
| Los Altos | shortest_frontage | 58 LYELL ST, Los Altos, CA | tyndall st | 1 / 2 | — | different_front | 2 FL edge(s) unmatched |
| Los Altos Hills | designated | 14100 DONELSON PL, Los Altos Hills, CA | donelson pl | 1 / 2 | front | futurelot_extra_front | — |
| Mountain View | shortest_frontage | 120 CHURCH ST, Mountain View, CA | calderon ave | 1 / 2 | front | futurelot_extra_front | — |
| Palo Alto | owner_elected | 589 COLERIDGE AV, Palo Alto, CA | coleridge ave | 1 / 2 | front | futurelot_extra_front | — |
| San Jose | shortest_frontage | 1098 MICHIGAN AV, San Jose, CA | michigan ave | 1 / 1 | front | agree | — |
| Saratoga | shortest_frontage | 19740 BRAEMAR DR, Saratoga, CA | braemar dr | 1 / 2 | front | futurelot_extra_front | — |
| Sunnyvale | all_fronts | 274 JACKSON ST, Sunnyvale, CA | jackson st | 2 / 3 | front | futurelot_extra_front | 1 FL edge(s) unmatched |
| Healdsburg | shortest_frontage | 407 MATHESON ST, Healdsburg, CA | matheson st | 1 / 1 | front | agree | — |
| Windsor | shortest_frontage | 491 MALLORY AVE, Windsor, CA | mallory ave | 1 / 1 | front | agree | 1 FL edge(s) unmatched |
| Contra Costa County (unincorporated) | all_fronts | 845  COVENTRY RD, KENSINGTON, CA | ardmore path | 1 / 3 | front | futurelot_extra_front | roads collapsed frontage; 3 FL edge(s) unmatched |
| Marin County (unincorporated) | address_street | 233 WOODLAND RD, KENTFIELD, CA | woodland rd | 1 / 2 | front | futurelot_extra_front | — |
| Napa County (unincorporated) | shortest_frontage | 481 NEWTON WAY, ANG, CA | toyon st | 1 / 1 | — | different_front | roads collapsed frontage; 2 FL edge(s) unmatched |
| Santa Clara County (unincorporated) | shortest_frontage | 99 CLEVELAND AV, SAN JOSE, CA | cleveland ave | 1 / 2 | front | futurelot_extra_front | — |
| Sonoma County (unincorporated) | owner_elected | 365 CALLE DEL MONTE, BOYES HOT SPRINGS, CA | calle del monte | 1 / 2 | front | futurelot_extra_front | — |

## Edge detail

### Lafayette — 680  GLENSIDE DR, Lafayette, CA

rule `designated` · zone `R-10` · same lot: True (centroid offset 16.9 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 78.1 | front | glenside dr | street | 96.1 | 3.0 |
| front | 16.9 | front | glenside dr | street | 96.1 | 2.9 |
| front | 17.1 | street_side | augustine ln | street | 96.3 | 0.6 |
| front | 79.4 | street_side | augustine ln | street | 96.3 | 3.3 |
| rear | 99.4 | rear | — | parcels | 99.0 | 2.4 |
| side | 79.5 | side | — | parcels | 79.5 | 3.2 |

### Moraga — 838  CAMINO RICARDO, Moraga, CA

rule `designated` · zone `3-DUA` · same lot: True (centroid offset 23.6 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 118.4 | rear | — | parcels | 118.5 | 3.7 |
| front | 87.1 | street_side | corliss dr | street | 97.9 | 1.0 |
| front | 12.4 | street_side | corliss dr | street | 97.9 | 0.7 |
| front | 8.5 | front | camino ricardo | street | 119.4 | 3.2 |
| front | 108.2 | front | camino ricardo | street | 119.4 | 4.3 |
| side | 90.8 | side | — | parcels | 90.3 | 0.9 |

### Orinda — 9  NORTHWOOD DR, Orinda, CA

rule `shortest_frontage` · zone `RL-20` · same lot: True (centroid offset 14.6 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 139.8 | side | — | parcels | 140.0 | 3.8 |
| front | 75.1 | front | northwood ct | street | 78.0 | 2.4 |
| front | 15.5 | street_side | northwood dr | street | 137.3 | 2.0 |
| front | 123.5 | street_side | northwood dr | street | 137.3 | 3.7 |
| side | 89.3 | rear | — | parcels | 89.1 | 0.2 |

### Fairfax — 73 SCENIC RD, Fairfax, CA

rule `shortest_frontage` · zone `RD-5.5-7` · same lot: True (centroid offset 5.0 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 73.8 | street_side | scenic rd | street | 111.4 | 3.3 |
| front | 56.6 | street_side | scenic rd | street | 111.4 | 0.6 |
| front | 48.3 | front | manor rd | street | 67.2 | 3.4 |
| rear | 114.9 | side | — | parcels | 114.7 | 2.1 |
| side | 49.8 | rear | — | parcels | 49.8 | 3.2 |

### Mill Valley — 329 ETHEL AVE, Mill Valley, CA

rule `designated` · zone `RS-6` · same lot: True (centroid offset 8.9 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| side | 32.6 | (unmatched) | — | — | — | — |
| side | 123.9 | rear | — | parcels | 123.3 | 0.1 |
| side | 48.1 | (unmatched) | — | — | — | — |
| side | 14.1 | front | ethel ave | street | 185.1 | 1.3 |
| side | 90.5 | front | ethel ave | street | 185.1 | 0.6 |

### Sausalito — 299 GLEN DR, Sausalito, CA

rule `owner_elected` · zone `R-1-6` · same lot: True (centroid offset 4.9 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| side | 75.7 | street_side | currey ave | street | 74.8 | 3.1 |
| front | 66.9 | front | glen dr | street | 66.6 | 3.1 |
| side | 61.8 | side | — | parcels | 61.9 | 3.2 |
| rear | 65 | rear | — | parcels | 65.6 | 2.4 |

### Napa — 1795 LAUREL ST, Napa, CA

rule `shortest_frontage` · zone `RT 5` · same lot: True (centroid offset 4.4 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 120.2 | street_side | jefferson st | street | 120.4 | 4.9 |
| front | 61 | front | laurel st | street | 61.0 | 1.3 |
| side | 117.6 | side | — | parcels | 117.8 | 3.7 |
| rear | 75.3 | rear | — | parcels | 75.3 | 1.4 |

### Atherton — 256 PRIOR LN, Atherton, CA

rule `address_street` · zone `R-1A` · same lot: True (centroid offset 53.3 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 251.3 | rear | — | parcels | 250.8 | 4.8 |
| front | 207.1 | street_side | middlefield rd | street | 224.3 | 0.6 |
| front | 16.9 | street_side | middlefield rd | street | 224.3 | 0.6 |
| front | 13.6 | front | prior ln | street | 245.5 | 2.3 |
| front | 231.4 | front | prior ln | street | 245.5 | 3.8 |
| side | 227.3 | side | — | parcels | 227.4 | 0.2 |

### Hillsborough — 5 HOMEPLACE CT, Hillsborough, CA

rule `all_fronts` · zone `R` · same lot: True (centroid offset 23.3 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 157.1 | street_side | barroilhet ave | street | 177.5 | 7.4 |
| rear | 171 | rear | — | parcels | 170.5 | 1.0 |
| side | 180.5 | side | — | parcels | 160.6 | 4.4 |
| front | 88.2 | front | homeplace ct | street | 105.8 | 3.2 |
| front | 18.1 | (unmatched) | — | — | — | — |

### Menlo Park — 385 OAK GROVE AVE, Menlo Park, CA

rule `owner_elected` · zone `R3` · same lot: True (centroid offset 10.7 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 128.5 | front | oak grove ave | street | 128.3 | 10.3 |
| side | 60 | side | — | parcels | 59.8 | 2.5 |
| rear | 128.5 | rear | — | parcels | 128.6 | 10.4 |
| front | 60 | street_side | laurel st | street | 60.0 | 2.6 |

### Portola Valley — 247 ECHO LN, Portola Valley, CA

rule `owner_elected` · zone `R-1/15M` · same lot: True (centroid offset 8.6 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| side | 200.1 | side | — | parcels | 199.7 | 2.2 |
| rear | 95.7 | rear | — | parcels | 95.7 | 2.7 |
| front | 199.9 | street_side | alpine rd | street | 199.5 | 2.3 |
| front | 67.3 | front | echo ln | street | 67.6 | 2.8 |

### San Carlos — 2000 BIRCH AVE, San Carlos, CA

rule `shortest_frontage` · zone `Single Family` · same lot: True (centroid offset 3.9 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 68.5 | rear | — | parcels | 69.1 | 4.7 |
| front | 100.1 | street_side | cordilleras ave | street | 100.9 | 0.4 |
| front | 75.1 | front | birch ave | street | 75.4 | 4.0 |
| side | 100 | side | — | parcels | 100.3 | 2.4 |

### San Mateo — 550 BARNESON AVE, San Mateo, CA

rule `owner_elected` · zone `R1C` · same lot: True (centroid offset 6.1 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 69.6 | rear | — | parcels | 68.5 | 4.3 |
| side | 87.1 | side | — | parcels | 86.7 | 4.7 |
| front | 69.4 | front | barneson ave | street | 68.5 | 4.5 |
| front | 87 | street_side | alameda de las | street | 87.2 | 3.8 |

### San Mateo County (unincorporated) — 843 6TH AVE, REDWOOD CITY, CA

rule `shortest_frontage` · zone `R-1/S-73` · same lot: True (centroid offset 9.7 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 100 | side | — | parcels | 99.9 | 4.2 |
| side | 50.8 | front | bay rd | street | 55.9 | 3.8 |
| front | 15.4 | street_side | sixth ave | street | 95.0 | 1.3 |
| front | 83.1 | street_side | sixth ave | street | 95.0 | 3.8 |
| side | 58.9 | rear | — | parcels | 58.5 | 2.1 |

### Los Altos — 58 LYELL ST, Los Altos, CA

rule `shortest_frontage` · zone `R3-1.8` · same lot: True (centroid offset 4.2 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 50.1 | (unmatched) | — | — | — | — |
| front | 141.9 | rear | — | parcels | 141.4 | 48.0 |
| side | 49.9 | (unmatched) | — | — | — | — |
| rear | 141.9 | rear | — | parcels | 141.4 | 1.6 |

### Los Altos Hills — 14100 DONELSON PL, Los Altos Hills, CA

rule `designated` · zone `R-A` · same lot: True (centroid offset 43.4 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 146.2 | front | donelson pl | street | 161.8 | 6.2 |
| side | 259.5 | side | — | parcels | 259.0 | 1.6 |
| rear | 167.2 | rear | — | parcels | 167.6 | 3.8 |
| front | 245.7 | street_side | fremont rd | street | 264.4 | 1.5 |
| front | 17.1 | street_side | fremont rd | street | 264.4 | 1.0 |
| front | 16.5 | front | donelson pl | street | 161.8 | 3.7 |

### Mountain View — 120 CHURCH ST, Mountain View, CA

rule `shortest_frontage` · zone `R3-1` · same lot: True (centroid offset 14.4 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| side | 77.3 | rear | — | parcels | 77.2 | 4.3 |
| rear | 103.1 | side | — | parcels | 103.0 | 0.1 |
| front | 77.1 | front | calderon ave | street | 86.3 | 4.2 |
| front | 7.9 | front | calderon ave | street | 86.3 | 3.7 |
| front | 99.9 | street_side | church st | street | 99.4 | 2.2 |

### Palo Alto — 589 COLERIDGE AV, Palo Alto, CA

rule `owner_elected` · zone `R-1 (10000)` · same lot: True (centroid offset 4.3 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 100 | rear | — | parcels | 100.2 | 4.1 |
| front | 120 | street_side | webster st | street | 119.9 | 1.1 |
| front | 100 | front | coleridge ave | street | 99.9 | 4.1 |
| side | 120 | side | — | parcels | 119.7 | 1.2 |

### San Jose — 1098 MICHIGAN AV, San Jose, CA

rule `shortest_frontage` · zone `R-2` · same lot: True (centroid offset 18.3 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 16.8 | front | michigan ave | street | 133.6 | 5.8 |
| front | 120 | front | michigan ave | street | 133.6 | 3.6 |
| side | 47.4 | side | — | parcels | 47.2 | 1.4 |
| rear | 142 | rear | — | parcels | 141.9 | 4.0 |
| side | 28.1 | street_side | lincoln ave | street | 44.0 | 1.5 |
| side | 12.1 | street_side | lincoln ave | street | 44.0 | 3.7 |

### Saratoga — 19740 BRAEMAR DR, Saratoga, CA

rule `shortest_frontage` · zone `R-1-10` · same lot: True (centroid offset 11.6 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 19.1 | (unmatched) | — | — | — | — |
| front | 82.8 | front | braemar dr | street | 95.4 | 3.6 |
| side | 117.8 | side | — | parcels | 118.1 | 2.5 |
| rear | 106.4 | rear | — | parcels | 106.1 | 3.5 |
| front | 50.7 | street_side | crestbrook dr | street | 117.0 | 3.6 |
| front | 59 | street_side | crestbrook dr | street | 117.0 | 4.0 |

### Sunnyvale — 274 JACKSON ST, Sunnyvale, CA

rule `all_fronts` · zone `R0` · same lot: True (centroid offset 4.9 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 33.1 | front | jackson st | street | 45.7 | 5.0 |
| front | 21.7 | (unmatched) | — | — | — | — |
| front | 96 | street_side | bayview ave | street | 106.4 | 1.6 |
| side | 50.1 | rear | — | parcels | 50.1 | 4.1 |
| rear | 113 | side | — | parcels | 112.7 | 0.6 |

### Healdsburg — 407 MATHESON ST, Healdsburg, CA

rule `shortest_frontage` · zone `R-1-6000` · same lot: True (centroid offset 3.7 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| side | 286.8 | side | — | parcels | 287.3 | 3.5 |
| rear | 50 | rear | — | parcels | 49.9 | 1.3 |
| side | 286.1 | side | — | parcels | 194.0 | 3.6 |
| front | 50 | front | matheson st | street | 49.9 | 1.1 |

### Windsor — 491 MALLORY AVE, Windsor, CA

rule `shortest_frontage` · zone `SR` · same lot: True (centroid offset 8.5 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| side | 76.5 | street_side | natalie dr | street | 94.6 | 3.7 |
| rear | 70.5 | rear | — | parcels | 70.4 | 1.5 |
| side | 100 | side | — | parcels | 100.3 | 3.4 |
| front | 44.8 | front | mallory ave | street | 62.6 | 1.4 |
| side | 35.8 | (unmatched) | — | — | — | — |

### Contra Costa County (unincorporated) — 845  COVENTRY RD, KENSINGTON, CA

rule `all_fronts` · zone `R-6 -TOV -K` · same lot: True (centroid offset 20.5 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 141.4 | (unmatched) | — | — | — | — |
| front | 21.4 | (unmatched) | — | — | — | — |
| front | 22.8 | front | ardmore path | street | 237.7 | 1.9 |
| front | 52.7 | (unmatched) | — | — | — | — |
| side | 146.1 | rear | — | parcels | 145.8 | 0.9 |
| rear | 54.3 | side | — | parcels | 54.2 | 3.5 |

### Marin County (unincorporated) — 233 WOODLAND RD, KENTFIELD, CA

rule `address_street` · zone `RSP-1` · same lot: True (centroid offset 16.7 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 218.4 | street_side | s ridgewood rd | street | 246.7 | 4.2 |
| front | 28.1 | street_side | s ridgewood rd | street | 246.7 | 6.4 |
| front | 24.7 | front | woodland rd | street | 275.5 | 4.4 |
| front | 250.7 | front | woodland rd | street | 275.5 | 0.7 |
| side | 185.8 | side | — | parcels | 265.8 | 4.0 |
| side | 79.6 | side | — | parcels | 265.8 | 3.9 |
| rear | 181.2 | rear | — | parcels | 276.3 | 1.6 |
| rear | 95.6 | rear | — | parcels | 276.3 | 0.5 |

### Napa County (unincorporated) — 481 NEWTON WAY, ANG, CA

rule `shortest_frontage` · zone `RS:B-5` · same lot: True (centroid offset 3.7 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 65.5 | (unmatched) | — | — | — | — |
| side | 74.9 | (unmatched) | — | — | — | — |
| front | 65.5 | side | — | parcels | 65.5 | 3.7 |
| side | 74.9 | rear | — | parcels | 74.9 | 0.2 |

### Santa Clara County (unincorporated) — 99 CLEVELAND AV, SAN JOSE, CA

rule `shortest_frontage` · zone `R1-n2` · same lot: True (centroid offset 4.5 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| front | 124.9 | street_side | olive ave | street | 124.7 | 1.9 |
| front | 45.3 | front | cleveland ave | street | 45.6 | 3.9 |
| side | 125.1 | side | — | parcels | 124.7 | 1.9 |
| rear | 46.6 | rear | — | parcels | 46.7 | 3.9 |

### Sonoma County (unincorporated) — 365 CALLE DEL MONTE, BOYES HOT SPRINGS, CA

rule `owner_elected` · zone `R1 B6 5 DU` · same lot: True (centroid offset 3.5 ft)

| FutureLot | ft | Engine | street | abuts | ft | offset ft |
|---|---|---|---|---|---|---|
| rear | 42.3 | rear | — | parcels | 42.4 | 3.8 |
| front | 81.5 | street_side | vallejo ave | street | 81.4 | 0.8 |
| front | 44.9 | front | calle del monte | street | 45.0 | 3.1 |
| side | 67 | side | — | parcels | 66.9 | 1.0 |

