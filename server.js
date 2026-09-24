import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

// Import backend routers
import regridRouter from './regrid-backend/index.js';
import lightboxRouter from './lightbox-backend/index.js';
import zoneomicsRouter from './zoneomics-backend/index.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 8080;

app.use(express.json());

// Mount API routers
app.use('/api/regrid', regridRouter);
app.use('/api/lightbox', lightboxRouter);
app.use('/api/zoneomics', zoneomicsRouter);

// Free open-data provider runs as a separate Flask process (gaudi-api-port/
// app_poc.py, port 3004); forward rather than mount. Mirrors the Vite dev proxy.
// On Render, scripts/render-start.sh starts that process in the same instance.
// 127.0.0.1, not localhost: Flask binds IPv4 loopback only.
const OPENDATA_URL = (process.env.OPENDATA_URL || 'http://127.0.0.1:3004').replace(/\/$/, '');
app.use('/api/opendata', async (req, res) => {
  let upstream;
  try {
    upstream = await fetch(`${OPENDATA_URL}${req.url}`, {
      method: req.method,
      headers: { 'Content-Type': 'application/json' },
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body ?? {}),
    });
  } catch {
    return res.status(502).json({ error: `opendata backend unreachable at ${OPENDATA_URL} (locally: npm run dev:opendata)` });
  }
  // Pass non-JSON replies (a Flask 404/500 HTML page) through instead of
  // masking them as "unreachable".
  const text = await upstream.text();
  res.status(upstream.status);
  try { res.json(JSON.parse(text)); }
  catch { res.type(upstream.headers.get('content-type') || 'text/plain').send(text); }
});

// Render health check (render.yaml healthCheckPath). 503 when the opendata
// provider is down, so a deploy whose Python side cannot start never goes live.
app.get('/healthz', async (req, res) => {
  try {
    const r = await fetch(`${OPENDATA_URL}/health`, { signal: AbortSignal.timeout(3000) });
    res.status(r.ok ? 200 : 503).json({ ok: r.ok, opendata: r.ok ? 'up' : `status ${r.status}` });
  } catch (err) {
    res.status(503).json({ ok: false, opendata: `unreachable (${err.name})` });
  }
});

// Serve static frontend
const distPath = path.join(__dirname, 'frontend', 'dist');
app.use(express.static(distPath));

// Project documents (the ADU setback decision tree + its PDF/PNG exports, the
// front-rule summaries) at /docs/<file>, straight from zoning-ordinances/, so a
// Linear ticket can link the live page and it stays current with the repo.
app.use('/docs', express.static(path.join(__dirname, 'zoning-ordinances'), { index: false }));

// SPA fallback: serve index.html for any non-API route
app.get('*', (req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
