# Regrid vs Lightbox Data Provider Comparison

Compare parcel data from Regrid and Lightbox side-by-side on a split-screen map.

## Structure

- **regrid-backend** – Express proxy for Regrid API (typeahead, parcels)
- **lightbox-backend** – Express proxy for Lightbox API (geocoding, parcels, structures, zoning)
- **frontend** – React + Vite app with Mapbox map, address autocomplete toggle, and split-pane comparison

## Setup

1. Copy `.env.example` to `.env` and add your API keys:
   - `REGRID_TOKEN` – Regrid API token
   - `LIGHTBOX_API_KEY` – Lightbox API key
   - `VITE_MAPBOX_TOKEN` – Mapbox access token

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run all services:
   ```bash
   npm run dev
   ```

   **If you see "address already in use" for port 3001 or 3002**, stop any old processes:
   ```bash
   lsof -ti:3001 | xargs kill -9
   lsof -ti:3002 | xargs kill -9
   ```
   Then run `npm run dev` again.

   Or run individually:
   - `npm run dev:regrid` – Regrid backend (port 3001)
   - `npm run dev:lightbox` – Lightbox backend (port 3002)
   - `npm run dev:frontend` – Frontend (port 5173)

## Verify Regrid token

If you get "Access denied" from Regrid:

1. **Test token from .env:** `node regrid-backend/debug-token.js`
2. **Test a specific token:** `node regrid-backend/debug-token.js YOUR_TOKEN` (paste the token from the Regrid sandbox Credentials field)
3. **With backend running:** `curl http://localhost:3001/verify-token`

If the sandbox works but .env fails, the token in .env may be wrong. Copy the exact token from [developer.regrid.com](https://developer.regrid.com) Credentials when you use "Try It"—that may differ from app.regrid.com.

## Usage

1. Open the frontend (e.g. http://localhost:5173)
2. Toggle between Regrid and Lightbox for address autocomplete
3. Type an address and select a suggestion
4. View full parcel data from both providers in the split-screen view
