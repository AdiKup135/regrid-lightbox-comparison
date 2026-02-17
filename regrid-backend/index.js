import dotenv from 'dotenv';
import express from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEBUG_LOG = path.resolve(__dirname, '../.cursor/debug.log');
function dbg(payload) { try { fs.mkdirSync(path.dirname(DEBUG_LOG), { recursive: true }); fs.appendFileSync(DEBUG_LOG, JSON.stringify(payload) + '\n'); } catch (_) {} }
dotenv.config({ path: path.resolve(__dirname, '../.env') });

function getRegridToken() {
  let t = (process.env.REGRID_TOKEN ?? '').trim();
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    t = t.slice(1, -1).trim();
  }
  return t;
}

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// HIFLD transmission lines (for map display) - must be before parametric routes
const HIFLD_TRANSMISSION_URL = 'https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0/query';

// FEMA National Flood Hazard Layer - Flood Hazard Zones (layer 28)
// Use gis/nfhl path (arcgis path can return fetch failed from server)
const FEMA_NFHL_URL = 'https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query';
app.get('/hifld/transmission-lines', async (req, res) => {
  const { minLon, minLat, maxLon, maxLat } = req.query;
  if (minLon == null || minLat == null || maxLon == null || maxLat == null) {
    return res.status(400).json({ error: 'minLon, minLat, maxLon, maxLat required' });
  }
  try {
    const geometry = JSON.stringify({ xmin: +minLon, ymin: +minLat, xmax: +maxLon, ymax: +maxLat });
    const url = new URL(HIFLD_TRANSMISSION_URL);
    url.searchParams.set('where', '1=1');
    url.searchParams.set('outFields', '*');
    url.searchParams.set('geometryType', 'esriGeometryEnvelope');
    url.searchParams.set('geometry', geometry);
    url.searchParams.set('inSR', '4326');
    url.searchParams.set('spatialRel', 'esriSpatialRelIntersects');
    url.searchParams.set('outSR', '4326');
    url.searchParams.set('resultRecordCount', '500');
    url.searchParams.set('f', 'geojson');
    // #region agent log
    dbg({ location: 'regrid-backend:hifld', message: 'HIFLD request', data: { minLon, minLat, maxLon, maxLat, url: url.toString() }, hypothesisId: 'A,E', timestamp: Date.now() });
    // #endregion
    const r = await fetch(url.toString());
    const data = await r.json();
    // #region agent log
    dbg({ location: 'regrid-backend:hifld', message: 'HIFLD response', data: { status: r.status, ok: r.ok, dataType: data?.type, featureCount: data?.features?.length, hasError: !!data?.error, dataKeys: data ? Object.keys(data) : [] }, hypothesisId: 'A,B,E', timestamp: Date.now() });
    // #endregion
    if (!r.ok) {
      return res.status(r.status).json(data);
    }
    res.json(data);
  } catch (err) {
    console.error('HIFLD transmission lines error:', err);
    // #region agent log
    dbg({ location: 'regrid-backend:hifld', message: 'HIFLD error', data: { err: String(err.message) }, hypothesisId: 'A', timestamp: Date.now() });
    // #endregion
    res.status(500).json({ error: 'Transmission lines request failed' });
  }
});

// FEMA flood hazard zones (for map display) - bbox in WGS84
app.get('/fema/flood-zones', async (req, res) => {
  const { minLon, minLat, maxLon, maxLat } = req.query;
  if (minLon == null || minLat == null || maxLon == null || maxLat == null) {
    return res.status(400).json({ error: 'minLon, minLat, maxLon, maxLat required' });
  }
  try {
    // #region agent log
    dbg({ location: 'regrid-backend:fema', message: 'FEMA request', data: { minLon, minLat, maxLon, maxLat }, hypothesisId: 'A,E', timestamp: Date.now() });
    // #endregion
    const geometry = JSON.stringify({ xmin: +minLon, ymin: +minLat, xmax: +maxLon, ymax: +maxLat });
    const url = new URL(FEMA_NFHL_URL);
    url.searchParams.set('where', '1=1');
    url.searchParams.set('outFields', 'FLD_ZONE,ZONE_SUBTY');
    url.searchParams.set('geometryType', 'esriGeometryEnvelope');
    url.searchParams.set('geometry', geometry);
    url.searchParams.set('inSR', '4326');
    url.searchParams.set('spatialRel', 'esriSpatialRelIntersects');
    url.searchParams.set('outSR', '4326');
    url.searchParams.set('resultRecordCount', '500');
    url.searchParams.set('f', 'geojson');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const r = await fetch(url.toString(), {
      headers: { 'User-Agent': 'RegridLightbox/1.0 (parcel comparison tool)' },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    const data = await r.json();
    // #region agent log
    dbg({ location: 'regrid-backend:fema', message: 'FEMA response', data: { status: r.status, ok: r.ok, dataType: data?.type, featureCount: data?.features?.length }, hypothesisId: 'A,B,E', timestamp: Date.now() });
    // #endregion
    if (!r.ok) return res.status(r.status).json(data);
    res.json(data);
  } catch (err) {
    console.error('FEMA flood zones error:', err);
    // #region agent log
    dbg({ location: 'regrid-backend:fema', message: 'FEMA error', data: { err: String(err.message) }, hypothesisId: 'A', timestamp: Date.now() });
    // #endregion
    res.status(500).json({ error: 'FEMA flood zones request failed' });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'regrid-backend' });
});

// Ready check (verifies API token is configured)
app.get('/ready', (req, res) => {
  const hasToken = !!process.env.REGRID_TOKEN;
  res.status(hasToken ? 200 : 503).json({
    ready: hasToken,
    message: hasToken ? 'Regrid token configured' : 'REGRID_TOKEN not set',
  });
});

// Token verification: test Regrid API with a known Dallas address
app.get('/verify-token', async (req, res) => {
  const token = getRegridToken();
  if (!token) {
    return res.status(503).json({ ok: false, error: 'REGRID_TOKEN not set' });
  }
  try {
    const url = new URL(`${REGRID_BASE}/parcels/typeahead`);
    url.searchParams.set('token', token);
    url.searchParams.set('query', '5818 Diana Dr');
    const r = await fetch(url.toString());
    const data = await r.json();
    if (r.ok && data?.parcel_centroids?.features?.length) {
      return res.json({ ok: true, message: 'Token works', count: data.parcel_centroids.features.length });
    }
    return res.status(401).json({
      ok: false,
      error: data?.message || 'Access denied',
      hint: 'Copy the token from the Regrid sandbox (developer.regrid.com) Credentials field—the sandbox may use a different token than .env. Test with: node regrid-backend/debug-token.js YOUR_TOKEN',
    });
  } catch (err) {
    return res.status(500).json({ ok: false, error: String(err.message) });
  }
});

const REGRID_BASE = 'https://app.regrid.com/api/v2';

// Typeahead (address autocomplete)
// OpenAPI spec: only query+token. Trial restricted to 7 counties.
app.get('/parcels/typeahead', async (req, res) => {
  const { query } = req.query;
  if (!query || typeof query !== 'string') {
    return res.status(400).json({ error: 'query parameter required' });
  }
  const token = getRegridToken();
  try {
    const url = new URL(`${REGRID_BASE}/parcels/typeahead`);
    url.searchParams.set('token', token);
    url.searchParams.set('query', query);
    const r = await fetch(url.toString());
    const data = await r.json();
    if (!r.ok) {
      return res.status(r.status).json(data);
    }
    res.json(data);
  } catch (err) {
    console.error('Regrid typeahead error:', err);
    res.status(500).json({ error: 'Regrid typeahead request failed' });
  }
});

// Full parcel by ll_uuid
app.get('/parcel/:ll_uuid', async (req, res) => {
  const { ll_uuid } = req.params;
  // #region agent log
  dbg({location:'regrid-backend:parcel',message:'Route hit',data:{ll_uuid,path:req.path},hypothesisId:'R1',timestamp:Date.now()});
  // #endregion
  if (!ll_uuid) {
    return res.status(400).json({ error: 'll_uuid required' });
  }
  try {
    let url = new URL(`${REGRID_BASE}/parcel/${ll_uuid}`);
    url.searchParams.set('token', getRegridToken());
    let r = await fetch(url.toString());
    let data = await r.json();
    // Fallback: try /parcels/ (plural) if /parcel/ returns 404
    if (!r.ok && r.status === 404) {
      url = new URL(`${REGRID_BASE}/parcels/${ll_uuid}`);
      url.searchParams.set('token', getRegridToken());
      r = await fetch(url.toString());
      data = await r.json();
    }
    // #region agent log
    dbg({location:'regrid-backend:response',message:'Regrid API response',data:{status:r.status,ok:r.ok,dataKeys:data?Object.keys(data):[],message:data?.message},hypothesisId:'R2',timestamp:Date.now()});
    // #endregion
    if (!r.ok) {
      return res.status(r.status).json(data);
    }
    res.json(data);
  } catch (err) {
    console.error('Regrid parcel error:', err);
    res.status(500).json({ error: 'Regrid parcel request failed' });
  }
});

// Parcels by point (lat, lon, optional radius)
app.get('/parcels/point', async (req, res) => {
  const { lat, lon, radius = 250 } = req.query;
  if (!lat || !lon) {
    return res.status(400).json({ error: 'lat and lon required' });
  }
  try {
    const url = new URL(`${REGRID_BASE}/parcels/point`);
    url.searchParams.set('token', getRegridToken());
    url.searchParams.set('lat', lat);
    url.searchParams.set('lon', lon);
    url.searchParams.set('radius', radius);
    const r = await fetch(url.toString());
    const data = await r.json();
    if (!r.ok) {
      return res.status(r.status).json(data);
    }
    res.json(data);
  } catch (err) {
    console.error('Regrid point error:', err);
    res.status(500).json({ error: 'Regrid point request failed' });
  }
});

app.listen(PORT, () => {
  console.log(`Regrid backend running on http://localhost:${PORT}`);
});
