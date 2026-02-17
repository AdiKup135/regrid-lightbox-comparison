import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

// Import backend routers
import regridRouter from './regrid-backend/index.js';
import lightboxRouter from './lightbox-backend/index.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 8080;

app.use(express.json());

// Mount API routers
app.use('/api/regrid', regridRouter);
app.use('/api/lightbox', lightboxRouter);

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
