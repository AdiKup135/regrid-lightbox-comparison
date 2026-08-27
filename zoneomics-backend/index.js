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
 * Call Zoneomics API. Auth via query param `api_key`.
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
    if (ok && (data?.zoning != null || data?.controls != null || Array.isArray(data?.features) || data?.data != null)) {
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

// Per-neighbor point queries are the expensive part of /edges (~1 call per
// neighbor). Cache full parcels by APN so same-block lookups reuse them.
const parcelCacheByApn = new Map(); // apn -> { parcel, ts }
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

function cacheGet(apn) {
  const hit = parcelCacheByApn.get(apn);
  if (!hit) return null;
  if (Date.now() - hit.ts > CACHE_TTL_MS) { parcelCacheByApn.delete(apn); return null; }
  return hit.parcel;
}
function cachePut(parcel) {
  if (parcel?.apn && parcel?.boundary) parcelCacheByApn.set(parcel.apn, { parcel, ts: Date.now() });
}

/**
 * GET /edges?address=<free-form>&radius=<m, default auto from parcel size>&maxNeighbors=<default 12>
 *
 * Orchestrates the three Zoneomics call shapes for edge-labeling:
 *  1. address -> subject parcel WITH boundary (data.parcels[0])
 *  2. lat/lng+radius -> neighbor centroids, NO boundaries
 *     (data.features[0].properties.parcels[])
 *  3. point query per neighbor centroid -> full parcel WITH boundary
 * Returns { geocode, subject, neighbors, meta, zone, callCount } — the input
 * contract of edge-labeling/edge-labeling.ts (labelEdges).
 */
router.get('/edges', async (req, res) => {
  const { address } = req.query;
  const explicitRadius = Number(req.query.radius) || 0; // 0 = auto (from subject parcel size)
  const maxNeighbors = Math.min(Number(req.query.maxNeighbors) || 12, 20);
  if (!address || typeof address !== 'string') {
    return res.status(400).json({ error: 'address query param required' });
  }
  let callCount = 0;
  try {
    // 1) address -> subject
    const r1 = await zoneomicsFetch('/v2/zoneDetail', { address: address.trim(), output_fields: 'parcels' });
    callCount++;
    if (!r1.ok) return res.status(r1.status).json({ error: 'Zoneomics address lookup failed', detail: r1.data });
    const subject = r1.data?.data?.parcels?.[0];
    const geocode = { lat: r1.data?.data?.lat, lng: r1.data?.data?.lng };
    const meta = r1.data?.data?.meta ?? null; // city_id / city_name -> jurisdiction rules lookup
    const zone = r1.data?.data?.zone_details ?? null;
    if (!subject?.boundary) {
      return res.status(404).json({ error: 'No parcel with boundary at this address (parcels output requires Enterprise tier)', detail: r1.data?.data ?? null });
    }
    cachePut(subject);

    // 2) radius -> neighbor centroid stubs (GeoJSON shape).
    // The radius query matches parcel CENTROIDS, not geometry — a bordering
    // parcel as large as the subject has its centroid roughly (subject reach +
    // its own reach) away. Auto radius = 2x the subject's max centroid->vertex
    // distance + 20 m buffer, clamped to [60, 200]. One doubling retry covers
    // neighborhoods where the borderers are much larger than the subject.
    let radius = Math.min(explicitRadius, 200);
    if (!radius) {
      const ringM = subject.boundary.match(/\(\(([^()]+)\)/);
      const reachM = ringM
        ? Math.max(...ringM[1].split(',').map((s) => {
            const [lng, lat] = s.trim().split(/\s+/).map(Number);
            return Math.hypot((lng - subject.lng) * 111320 * Math.cos((subject.lat * Math.PI) / 180), (lat - subject.lat) * 111320);
          }))
        : 0;
      radius = Math.min(200, Math.max(60, Math.ceil(2 * reachM + 20)));
    }
    let unique = [];
    for (let attempt = 0; attempt < 2; attempt++) {
      const r2 = await zoneomicsFetch('/v2/zoneDetail', { lat: subject.lat, lng: subject.lng, radius: String(radius), output_fields: 'parcels' });
      callCount++;
      const features = r2.ok ? (r2.data?.data?.features ?? []) : [];
      const stubs = features
        .flatMap((f) => f?.properties?.parcels ?? [])
        .filter((p) => p && p.apn && p.apn !== subject.apn && typeof p.lat === 'number' && typeof p.lng === 'number');
      const seen = new Set();
      unique = stubs.filter((p) => (seen.has(p.apn) ? false : (seen.add(p.apn), true)));
      if (unique.length >= 3 || radius >= 200 || explicitRadius) break;
      radius = Math.min(200, radius * 2);
    }
    unique.sort((a, b) => ((a.lat - subject.lat) ** 2 + (a.lng - subject.lng) ** 2) - ((b.lat - subject.lat) ** 2 + (b.lng - subject.lng) ** 2));
    const targets = unique.slice(0, maxNeighbors);

    // 3) point query per neighbor for its boundary (parallel, cached by APN)
    const neighbors = (await Promise.all(targets.map(async (stub) => {
      const cached = cacheGet(stub.apn);
      if (cached) return cached;
      const r3 = await zoneomicsFetch('/v2/zoneDetail', { lat: stub.lat, lng: stub.lng, output_fields: 'parcels' });
      callCount++;
      if (!r3.ok) return null;
      const parcels = r3.data?.data?.parcels ?? [];
      const match = parcels.find((q) => q.apn === stub.apn) ?? parcels[0] ?? null;
      if (match?.boundary) { cachePut(match); return match; }
      return null;
    }))).filter(Boolean);

    res.json({ geocode, subject, neighbors, meta, zone, callCount, radius, droppedStubs: unique.length - targets.length });
  } catch (err) {
    console.error('Zoneomics edges error:', err);
    res.status(500).json({ error: 'Zoneomics edges request failed', callCount });
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
    console.log(`Zoneomics backend running on http://localhost:${PORT}`);
  });
}

export default router;
