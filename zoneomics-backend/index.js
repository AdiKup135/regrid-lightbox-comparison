import dotenv from 'dotenv';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const router = express.Router();

const ZONEOMICS_BASE = 'https://api.zoneomics.com/v2';

function getApiKey() {
  const key = (process.env.ZONEOMICS_API_KEY ?? '').trim();
  if ((key.startsWith('"') && key.endsWith('"')) || (key.startsWith("'") && key.endsWith("'"))) {
    return key.slice(1, -1).trim();
  }
  return key;
}

async function zoneomicsFetch(reqPath, searchParams = {}) {
  const key = getApiKey();
  if (!key) throw new Error('ZONEOMICS_API_KEY not set');
  const url = new URL(`${ZONEOMICS_BASE}${reqPath}`);
  url.searchParams.set('api_key', key);
  Object.entries(searchParams).forEach(([k, v]) => {
    if (v != null && v !== '') url.searchParams.set(k, v);
  });
  const r = await fetch(url.toString());
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, status: r.status, data };
  return { ok: true, status: r.status, data };
}

// Per-neighbor point queries are the expensive part (~1 call per neighbor).
// Cache full parcels by APN so same-block lookups reuse them.
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

/**
 * GET /edges?address=<free-form>&radius=<m, default 60>&maxNeighbors=<default 12>
 *
 * Orchestrates the three Zoneomics call shapes (verified live 2026-08-27):
 *  1. address -> subject parcel WITH boundary (data.parcels[0])
 *  2. lat/lng+radius -> neighbor centroids, NO boundaries
 *     (data.features[0].properties.parcels[])
 *  3. point query per neighbor centroid -> full parcel WITH boundary
 * Returns { geocode, subject, neighbors, meta, callCount } — exactly the
 * input contract of edge-labeling/edge-labeling.ts (labelEdges).
 */
router.get('/edges', async (req, res) => {
  const { address } = req.query;
  const radius = Math.min(Number(req.query.radius) || 60, 200);
  const maxNeighbors = Math.min(Number(req.query.maxNeighbors) || 12, 20);
  if (!address || typeof address !== 'string') {
    return res.status(400).json({ error: 'address query param required' });
  }
  let callCount = 0;
  try {
    // 1) address -> subject
    const r1 = await zoneomicsFetch('/zoneDetail', { address: address.trim(), output_fields: 'parcels' });
    callCount++;
    if (!r1.ok) return res.status(r1.status).json({ error: 'Zoneomics address lookup failed', detail: r1.data });
    const subject = r1.data?.data?.parcels?.[0];
    const geocode = { lat: r1.data?.data?.lat, lng: r1.data?.data?.lng };
    const meta = r1.data?.data?.meta ?? null; // city_id / city_name / last_updated -> jurisdiction match
    const zone = r1.data?.data?.zone_details ?? null;
    if (!subject?.boundary) {
      return res.status(404).json({ error: 'No parcel with boundary at this address (parcels output requires Enterprise tier)', detail: r1.data?.data ?? null });
    }
    cachePut(subject);

    // 2) radius -> neighbor centroid stubs (GeoJSON shape)
    const r2 = await zoneomicsFetch('/zoneDetail', { lat: subject.lat, lng: subject.lng, radius: String(radius), output_fields: 'parcels' });
    callCount++;
    const features = r2.ok ? (r2.data?.data?.features ?? []) : [];
    const stubs = features
      .flatMap((f) => f?.properties?.parcels ?? [])
      .filter((p) => p && p.apn && p.apn !== subject.apn && typeof p.lat === 'number' && typeof p.lng === 'number');
    // De-dup by APN, sort by distance to subject centroid, cap the fan-out.
    const seen = new Set();
    const unique = stubs.filter((p) => (seen.has(p.apn) ? false : (seen.add(p.apn), true)));
    unique.sort((a, b) => ((a.lat - subject.lat) ** 2 + (a.lng - subject.lng) ** 2) - ((b.lat - subject.lat) ** 2 + (b.lng - subject.lng) ** 2));
    const targets = unique.slice(0, maxNeighbors);

    // 3) point query per neighbor for its boundary (parallel, cached by APN)
    const neighbors = (await Promise.all(targets.map(async (stub) => {
      const cached = cacheGet(stub.apn);
      if (cached) return cached;
      const r3 = await zoneomicsFetch('/zoneDetail', { lat: stub.lat, lng: stub.lng, output_fields: 'parcels' });
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
