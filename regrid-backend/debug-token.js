#!/usr/bin/env node
/**
 * Test Regrid token.
 * Run: node regrid-backend/debug-token.js           # uses .env
 * Run: node regrid-backend/debug-token.js YOUR_TOKEN  # test a specific token
 */
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
let token;

if (process.argv[2]) {
  token = process.argv[2].trim();
  console.log('Using token from command line, len=', token.length);
} else {
  const envPath = path.resolve(__dirname, '../.env');
  console.log('Loading .env from:', envPath);
  const result = dotenv.config({ path: envPath });
  if (result.error) {
    console.error('dotenv error:', result.error.message);
    process.exit(1);
  }
  const raw = process.env.REGRID_TOKEN ?? '';
  token = raw.trim().replace(/^["']|["']$/g, '');
  console.log('REGRID_TOKEN from .env: len=', token.length);
}

const url = `https://app.regrid.com/api/v2/parcels/typeahead?token=${encodeURIComponent(token)}&query=3122%20Carlson%20Dr`;

const r = await fetch(url);
const data = await r.json();
console.log('Status:', r.status, r.statusText);
console.log('Response:', JSON.stringify(data, null, 2).slice(0, 500));
