# site repo — architecture map

*POC repo. Main-only, no branches. Last updated 2026-08-30.*

This repo started as a Regrid-vs-Lightbox data-provider comparison (the README's
original story) and grew into the staging ground for the **parcel edge-labeling
pipeline** headed for production (`repos/Gaudi/gaudi-api`). This file is the map.

## The one-paragraph version

Type an address in the debug UI → a **data provider** fetches the subject parcel,
its neighbor fabric, jurisdiction, and zone (the `/edges` wire shape) → the
**edge-labeling engine** tags every lot edge `front / street_side / side / rear`
under the jurisdiction's legal front rule → the UI draws it. Everything
Gaudi-bound is Python in `gaudi-api-port/`, written to gaudi-api conventions.

## Directory map

| Directory | What it is | Fate |
|---|---|---|
| `frontend/` | Vite/React debug UI. `App.tsx` = compare mode (Regrid/Lightbox panels); `EdgesPanel.tsx` = edges mode with **source toggle** (opendata / zoneomics) and **engine toggle** (Python server / TS client) | POC only |
| `gaudi-api-port/` | **The production-bound Python.** Engine + free data provider + Flask routes, mirroring gaudi-api layout. See its `README.md` + `HANDOFF.md` | Drops into gaudi-api |
| `edge-labeling/` | Original TS engine + `SPEC.md`. Kept as the differential reference (`gaudi-api-port/verification/`: 101 cases, 0 diffs) | Retire after Gaudi integration |
| `zoneomics-backend/` | Express: Zoneomics fetch orchestration (`/edges`), label bridge (`/edges/label` → Python via subprocess), offline fixtures. Quota-limited; budget guard | POC only |
| `regrid-backend/`, `lightbox-backend/` | The original comparison providers | POC only |
| `zoning-ordinances/` | **Jurisdiction database**: `zoning_ordinance_links.json` (23 jurisdictions, front rules, code-cited) + counsel-approved summaries | Moves with the engine |
| `json snadbox/` [sic] | Raw API captures, provider comparison notes | Scratch |

## The two data providers (same `/edges` wire shape)

```
                       ┌───────────────────────────────┐
 address ──────────────│  zoneomics  (Express :3003)   │──┐
                       │  quota-limited, budget guard  │  │   { geocode, subject,
                       └───────────────────────────────┘  ├──   neighbors, meta,
                       ┌───────────────────────────────┐  │     zone, callCount,
 address (+lat/lng) ───│  opendata   (Flask   :3004)   │──┘     flags }
                       │  free: Google/Census geocode →│
                       │  county ArcGIS parcel fabric →│           │
                       │  CA statewide zoning (OPR)    │           ▼
                       └───────────────────────────────┘   POST /edges/label
                                                            (either backend)
                                                                   │
                                                          Python engine labels
                                                          edges under the
                                                          jurisdiction front rule
```

**opendata** is the Zoneomics replacement built 2026-08-30 after the quota burn:
- Geocoding: caller lat/lng (Gaudi: `Project.address`, already Google) or Google
  Geocoding (`GOOGLE_API_KEY` required otherwise — the Census address-matching
  fallback and its situs string-matching heuristics were removed as unreliable).
  Jurisdiction/county always from Census point-containment (TIGER polygons).
- Parcels: per-county ArcGIS REST layers (6 counties cover all 23 jurisdictions),
  registry in `gaudi-api-port/services/parcel_data/county_registry.py`.
  Neighbors in ONE envelope query (vs Zoneomics' irreducible 2+N).
- Zone: CA statewide zoning layer (Gov-OPR), point query; vintage flagged.
- All keyless except the optional Google step. Degradations are flags
  (`neighbor_fetch_failed`, `subject_by_situs_search`, …), never silent.

## Ports & scripts

| Port | Service | Script |
|---|---|---|
| 5173 | Vite dev UI (proxies `/api/*`) | `npm run dev:frontend` |
| 3001/3002 | regrid / lightbox | `npm run dev:regrid` / `dev:lightbox` |
| 3003 | zoneomics backend | `npm run dev:zoneomics` |
| 3004 | opendata backend (Flask) | `npm run dev:opendata` |
| — | all of the above | `npm run dev` |

Tests: `cd gaudi-api-port && python3 -m pytest tests` (engine + provider, offline).

## What translates to Gaudi (and what doesn't)

Moves nearly as-is: `gaudi-api-port/services/compute/parcel_edges/` (engine),
`services/parcel_data/` (free provider), `routes/parcel_edges.py` (+
`@login_required` + two lines in `application.py`), the jurisdiction JSON.
Never moves: `app_poc.py`, the Express backends, the frontend, the TS engine.
Full integration brief: `gaudi-api-port/HANDOFF.md`.
