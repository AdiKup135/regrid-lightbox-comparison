import dotenv from 'dotenv';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const router = express.Router();

const ZONEOMICS_BASE = (process.env.ZONEOMICS_BASE_URL || 'https://api.zoneomics.com').replace(/\/$/, '');

function getApiKey() {
  const key = (process.env.ZONEOMICS_API_KEY ?? '').trim();
  if ((key.startsWith('"') && key.endsWith('"')) || (key.startsWith("'") && key.endsWith("'"))) {
    return key.slice(1, -1).trim();
  }
  return key;
}

/**
 * Call Zoneomics API. Auth via query param `api_key` (per https://www.zoneomics.com/docs/v2/zoning-point).
 */
async function zoneomicsFetch(reqPath, searchParams = {}) {
  const key = getApiKey();
  if (!key) throw new Error('ZONEOMICS_API_KEY not set');
  const url = new URL(`${ZONEOMICS_BASE}${reqPath}`);
  url.searchParams.set('api_key', key);
  Object.entries(searchParams).forEach(([k, v]) => {
    if (v != null && v !== '') url.searchParams.set(k, String(v));
  });
  const r = await fetch(url.toString());
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, status: r.status, data };
  return { ok: true, status: r.status, data };
}

router.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'zoneomics-backend' });
});

router.get('/ready', (req, res) => {
  const hasKey = !!getApiKey();
  res.status(hasKey ? 200 : 503).json({
    ready: hasKey,
    message: hasKey ? 'Zoneomics API key configured' : 'ZONEOMICS_API_KEY not set',
  });
});

router.get('/verify-key', async (req, res) => {
  try {
    const { ok, status, data } = await zoneomicsFetch('/v2/zoneDetail', {
      lat: 33.8158919,
      lng: -118.3888138,
    });
    if (ok && (data?.zoning != null || data?.controls != null || Array.isArray(data?.features))) {
      return res.json({ ok: true, message: 'Zoneomics key works' });
    }
    return res.status(401).json({
      ok: false,
      error: data?.error?.message || data?.message || `Zoneomics API returned ${status}`,
      hint: 'Check ZONEOMICS_API_KEY in .env.',
    });
  } catch (err) {
    return res.status(500).json({ ok: false, error: String(err.message) });
  }
});

// Proxy v2/conditionalControls – forward query params (e.g. lat, lng or address)
router.get('/v2/conditionalControls', async (req, res) => {
  try {
    const params = { ...req.query };
    const { ok, status, data } = await zoneomicsFetch('/v2/conditionalControls', params);
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    const errMsg = err?.message ?? String(err);
    const causeMsg = err?.cause?.message ?? err?.cause?.code;
    console.error('Zoneomics conditionalControls error:', err);
    const fullMsg = [errMsg, causeMsg].filter(Boolean).join('; ');
    res.status(500).json({ error: `Zoneomics conditional controls request failed: ${fullMsg || 'unknown'}`, detail: fullMsg || errMsg });
  }
});

// Proxy v2/zoneDetail for zoning comparison (lat/lng or address, optional output_fields)
router.get('/v2/zoneDetail', async (req, res) => {
  try {
    const params = { ...req.query };
    const { ok, status, data } = await zoneomicsFetch('/v2/zoneDetail', params);
    if (!ok) return res.status(status).json(data);
    res.json(data);
  } catch (err) {
    const errMsg = err?.message ?? String(err);
    const causeMsg = err?.cause?.message ?? err?.cause?.code;
    console.error('Zoneomics zoneDetail error:', err);
    const fullMsg = [errMsg, causeMsg].filter(Boolean).join('; ');
    res.status(500).json({ error: `Zoneomics zone detail request failed: ${fullMsg || 'unknown'}`, detail: fullMsg || errMsg });
  }
});

// Standalone mode for local dev
const _isMain = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (_isMain) {
  const app = express();
  const PORT = process.env.PORT || 3003;
  app.use(cors());
  app.use(express.json());
  app.use('/', router);
  app.listen(PORT, () => {
    const envPath = path.resolve(__dirname, '../.env');
    console.log(`Zoneomics backend running on http://localhost:${PORT} (loaded .env from ${envPath})`);
    if (!getApiKey()) {
      console.warn('ZONEOMICS_API_KEY is not set — Zoneomics API requests will fail. Add it to the project root .env.');
    }
  });
}

export default router;
