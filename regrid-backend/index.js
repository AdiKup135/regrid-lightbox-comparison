import dotenv from 'dotenv';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, '../.env') });

function getRegridToken() {
  let t = (process.env.REGRID_TOKEN ?? '').trim();
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    t = t.slice(1, -1).trim();
  }
  return t;
}

const router = express.Router();

const HIFLD_TRANSMISSION_URL = 'https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0/query';
const FEMA_NFHL_URL = 'https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query';
const REGRID_BASE = 'https://app.regrid.com/api/v2';

router.get('/hifld/transmission-lines', async (req, res) => {
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
    const r = await fetch(url.toString());
    const data = await r.json();
    if (!r.ok) return res.status(r.status).json(data);
    res.json(data);
  } catch (err) {
    console.error('HIFLD transmission lines error:', err);
    res.status(500).json({ error: 'Transmission lines request failed' });
  }
});

router.get('/fema/flood-zones', async (req, res) => {
  const { minLon, minLat, maxLon, maxLat } = req.query;
  if (minLon == null || minLat == null || maxLon == null || maxLat == null) {
    return res.status(400).json({ error: 'minLon, minLat, maxLon, maxLat required' });
  }
  try {
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
    if (!r.ok) return res.status(r.status).json(data);
    res.json(data);
  } catch (err) {
    console.error('FEMA flood zones error:', err);
    res.status(500).json({ error: 'FEMA flood zones request failed' });
  }
});

router.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'regrid-backend' });
});

router.get('/ready', (req, res) => {
  const hasToken = !!process.env.REGRID_TOKEN;
  res.status(hasToken ? 200 : 503).json({
    ready: hasToken,
    message: hasToken ? 'Regrid token configured' : 'REGRID_TOKEN not set',
  });
});

router.get('/verify-token', async (req, res) => {
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
      hint: 'Copy the token from the Regrid sandbox (developer.regrid.com) Credentials field.',
    });
  } catch (err) {
    return res.status(500).json({ ok: false, error: String(err.message) });
  }
});

router.get('/parcels/typeahead', async (req, res) => {
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
    if (!r.ok) return res.status(r.status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Regrid typeahead error:', err);
    res.status(500).json({ error: 'Regrid typeahead request failed' });
  }
});

router.get('/parcel/:ll_uuid', async (req, res) => {
  const { ll_uuid } = req.params;
  if (!ll_uuid) {
    return res.status(400).json({ error: 'll_uuid required' });
  }
  try {
    let url = new URL(`${REGRID_BASE}/parcel/${ll_uuid}`);
    url.searchParams.set('token', getRegridToken());
    let r = await fetch(url.toString());
    let data = await r.json();
    if (!r.ok && r.status === 404) {
      url = new URL(`${REGRID_BASE}/parcels/${ll_uuid}`);
      url.searchParams.set('token', getRegridToken());
      r = await fetch(url.toString());
      data = await r.json();
    }
    if (!r.ok) return res.status(r.status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Regrid parcel error:', err);
    res.status(500).json({ error: 'Regrid parcel request failed' });
  }
});

router.get('/parcels/point', async (req, res) => {
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
    if (!r.ok) return res.status(r.status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Regrid point error:', err);
    res.status(500).json({ error: 'Regrid point request failed' });
  }
});

// OSM fire hydrants & extinguishers via Overpass API
const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

router.get('/osm/fire-safety', async (req, res) => {
  const { lat, lon, radius = 500 } = req.query;
  if (lat == null || lon == null) {
    return res.status(400).json({ error: 'lat and lon required' });
  }
  try {
    const query = `[out:json][timeout:10];(node["emergency"="fire_hydrant"](around:${+radius},${+lat},${+lon});node["emergency"="fire_extinguisher"](around:${+radius},${+lat},${+lon}););out body;`;
    const r = await fetch(OVERPASS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `data=${encodeURIComponent(query)}`,
    });
    const data = await r.json();
    const elements = data?.elements ?? [];
    let nearestDistanceM = null;
    const features = elements.map((el) => {
      const dist = haversineM(+lat, +lon, el.lat, el.lon);
      if (nearestDistanceM === null || dist < nearestDistanceM) nearestDistanceM = dist;
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [el.lon, el.lat] },
        properties: { ...el.tags, osmId: el.id, distanceM: Math.round(dist) },
      };
    });
    res.json({ type: 'FeatureCollection', features, nearestDistanceM: nearestDistanceM != null ? Math.round(nearestDistanceM) : null });
  } catch (err) {
    console.error('OSM fire-safety error:', err);
    res.status(500).json({ error: 'OSM fire-safety request failed' });
  }
});

// Standalone mode for local dev
const _isMain = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (_isMain) {
  const app = express();
  const PORT = process.env.PORT || 3001;
  app.use(cors());
  app.use(express.json());
  app.use('/', router);
  app.listen(PORT, () => {
    console.log(`Regrid backend running on http://localhost:${PORT}`);
  });
}

export default router;
