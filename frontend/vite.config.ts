import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  envDir: '..', // load .env from monorepo root (site/)
  plugins: [react()],
  optimizeDeps: {
    include: ['mapbox-gl'],
  },
  server: {
    port: Number(process.env.PORT) || 5173,
    proxy: {
      '/api/regrid': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/regrid/, '/'),
      },
      '/api/lightbox': {
        target: 'http://localhost:3002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/lightbox/, '/'),
      },
      '/api/zoneomics': {
        target: 'http://localhost:3003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/zoneomics/, '/'),
      },
      // Free open-data provider (Flask, gaudi-api-port/app_poc.py).
      // Rewrite to '' (not '/'): Flask 404s the double slash Express tolerates.
      '/api/opendata': {
        target: 'http://localhost:3004',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/opendata/, ''),
      },
    },
  },
});
