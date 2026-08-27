/** One-off test: load .env and call Zoneomics conditionalControls. Run: node zoneomics-backend/test-fetch.js */
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, '../.env') });
const key = (process.env.ZONEOMICS_API_KEY ?? '').trim();
const base = (process.env.ZONEOMICS_BASE_URL || 'https://api.zoneomics.com').replace(/\/$/, '');
const url = `${base}/v2/conditionalControls?api_key=${encodeURIComponent(key)}&lat=34.2811157&lng=-119.2941656`;

console.log('ZONEOMICS_API_KEY set:', !!key);
try {
  const r = await fetch(url);
  console.log('Status:', r.status);
  const text = await r.text();
  console.log('Body (first 400):', text.slice(0, 400));
} catch (err) {
  console.log('ERROR:', err?.message, err?.cause?.message ?? err?.cause?.code);
}
