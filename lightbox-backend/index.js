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

const app = express();
const PORT = process.env.PORT || 3002;

app.use(cors());
app.use(express.json());

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'lightbox-backend' });
});

// Ready check (verifies API key is configured)
app.get('/ready', (req, res) => {
  const hasKey = !!process.env.LIGHTBOX_API_KEY;
  res.status(hasKey ? 200 : 503).json({
    ready: hasKey,
    message: hasKey ? 'Lightbox API key configured' : 'LIGHTBOX_API_KEY not set',
  });
});

// Verify key: test autocomplete with a known address
app.get('/verify-key', async (req, res) => {
  try {
    const { ok, status, data } = await lightboxFetch('/addresses/_autocomplete', {
      text: '5201 California Ave, Irvine CA',
      countryCode: 'US',
    });
    if (ok && data?.addresses?.length) {
      return res.json({ ok: true, message: 'Lightbox key works', count: data.addresses.length });
    }
    return res.status(401).json({
      ok: false,
      error: data?.error?.message || `Lightbox API returned ${status}`,
      hint: 'Check LIGHTBOX_API_KEY in .env. If you have a Consumer Secret, add LIGHTBOX_API_SECRET.',
    });
  } catch (err) {
    return res.status(500).json({ ok: false, error: String(err.message) });
  }
});

const LIGHTBOX_BASE = 'https://api.lightboxre.com/v1';

function getApiKey() {
  const key = (process.env.LIGHTBOX_API_KEY ?? '').trim();
  if ((key.startsWith('"') && key.endsWith('"')) || (key.startsWith("'") && key.endsWith("'"))) {
    return key.slice(1, -1).trim();
  }
  return key;
}

function getApiSecret() {
  const s = (process.env.LIGHTBOX_API_SECRET ?? '').trim();
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1).trim();
  }
  return s;
}

async function lightboxFetch(path, searchParams = {}) {
  const key = getApiKey();
  if (!key) throw new Error('LIGHTBOX_API_KEY not set');
  const url = new URL(`${LIGHTBOX_BASE}${path}`);
  Object.entries(searchParams).forEach(([k, v]) => {
    if (v != null && v !== '') url.searchParams.set(k, v);
  });
  const headers = { 'x-api-key': key };
  const secret = getApiSecret();
  if (secret) headers['x-api-secret'] = secret;
  const r = await fetch(url.toString(), { headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, status: r.status, data };
  return { ok: true, status: r.status, data };
}

// Geocoding autocomplete (type-ahead)
app.get('/addresses/_autocomplete', async (req, res) => {
  const { text, countryCode, bbox } = req.query;
  if (!text || typeof text !== 'string') {
    return res.status(400).json({ error: 'text parameter required' });
  }
  try {
    const { ok, status, data } = await lightboxFetch('/addresses/_autocomplete', {
      text: text.trim(),
      countryCode: countryCode || 'US',
      bbox,
    });
    // Lightbox returns 404 when no addresses match; normalize to 200 + empty array for better UX
    if (!ok && status === 404) {
      return res.json({ addresses: [], $ref: '', $metadata: { recordSet: { totalRecords: 0, bbox: {} } } });
    }
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Lightbox autocomplete error:', err);
    res.status(500).json({ error: 'Lightbox autocomplete request failed' });
  }
});

// Parcels by geometry (point with buffer)
app.get('/parcels/us/geometry', async (req, res) => {
  const { wkt, bufferDistance = 50, bufferUnit = 'm', limit, offset } = req.query;
  // #region agent log
  dbg({location:'lightbox-backend:parcels/geometry',message:'Route hit',data:{wkt,path:req.path,query:req.query},hypothesisId:'H1',timestamp:Date.now()});
  // #endregion
  if (!wkt || typeof wkt !== 'string') {
    return res.status(400).json({ error: 'wkt parameter required (e.g. POINT(lon lat))' });
  }
  try {
    const params = { wkt, bufferDistance: bufferDistance || 50, bufferUnit: bufferUnit || 'm', limit, offset };
    // #region agent log
    dbg({location:'lightbox-backend:params',message:'Params to Lightbox API',data:{wkt,bufferDistance:params.bufferDistance,bufferUnit:params.bufferUnit},hypothesisId:'H2',timestamp:Date.now()});
    // #endregion
    const { ok, status, data } = await lightboxFetch('/parcels/us/geometry', params);
    // #region agent log
    dbg({location:'lightbox-backend:response',message:'Lightbox API response',data:{ok,status,dataKeys:data?Object.keys(data):[],error:data?.error},hypothesisId:'H3',timestamp:Date.now()});
    // #endregion
    // Lightbox returns 404 when no parcels in buffer; normalize to 200 + empty array
    if (!ok && status === 404) {
      return res.json({ parcels: [], $ref: '', $metadata: { recordSet: { totalRecords: 0, bbox: {} } } });
    }
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Lightbox parcels geometry error:', err);
    res.status(500).json({ error: 'Lightbox parcels request failed' });
  }
});

// Structures on parcel (building footprints for parcel)
app.get('/structures/_on/parcel/us/:id', async (req, res) => {
  const { id } = req.params;
  if (!id || typeof id !== 'string') {
    return res.status(400).json({ error: 'id parameter required (parcel LightBox ID)' });
  }
  try {
    const { ok, status, data } = await lightboxFetch(`/structures/_on/parcel/us/${encodeURIComponent(id)}`);
    if (!ok && status === 404) {
      return res.json({ structures: [], $ref: '', $metadata: { recordSet: { totalRecords: 0, bbox: {} } } });
    }
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Lightbox structures on parcel error:', err);
    res.status(500).json({ error: 'Lightbox structures request failed' });
  }
});

// FEMA National Flood Hazard Layer for parcel
app.get('/nfhls/_on/parcel/us/:id', async (req, res) => {
  const { id } = req.params;
  if (!id || typeof id !== 'string') {
    return res.status(400).json({ error: 'id parameter required (parcel LightBox ID)' });
  }
  try {
    const { ok, status, data } = await lightboxFetch(`/nfhls/_on/parcel/us/${encodeURIComponent(id)}`);
    if (!ok && status === 404) {
      return res.json({ nfhls: [], $ref: '', $metadata: { recordSet: { totalRecords: 0 } } });
    }
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Lightbox FEMA NFHL on parcel error:', err);
    res.status(500).json({ error: 'FEMA flood data request failed' });
  }
});

// Parcels by address (one-shot: address string -> parcel)
app.get('/parcels/address', async (req, res) => {
  const { text } = req.query;
  if (!text || typeof text !== 'string') {
    return res.status(400).json({ error: 'text parameter required' });
  }
  try {
    const { ok, status, data } = await lightboxFetch('/parcels/address', { text: text.trim() });
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    console.error('Lightbox parcels address error:', err);
    res.status(500).json({ error: 'Lightbox parcels by address request failed' });
  }
});

app.listen(PORT, () => {
  console.log(`Lightbox backend running on http://localhost:${PORT}`);
});
