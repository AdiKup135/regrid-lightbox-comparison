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
const OPENDATA_URL = process.env.OPENDATA_URL || 'http://localhost:3004';
app.use('/api/opendata', async (req, res) => {
  try {
    const upstream = await fetch(`${OPENDATA_URL}${req.url}`, {
      method: req.method,
      headers: { 'Content-Type': 'application/json' },
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body ?? {}),
    });
    res.status(upstream.status).json(await upstream.json());
  } catch {
    res.status(502).json({ error: 'opendata backend unreachable (start it with npm run dev:opendata)' });
  }
});

// Serve static frontend
const distPath = path.join(__dirname, 'frontend', 'dist');
app.use(express.static(distPath));

// SPA fallback: serve index.html for any non-API route
app.get('*', (req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
