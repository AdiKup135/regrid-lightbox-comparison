import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  envDir: '..', // load .env from monorepo root (site/)
  plugins: [react()],
  optimizeDeps: {
    include: ['mapbox-gl'],
  },
  server: {
    port: 5173,
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
    },
  },
});
