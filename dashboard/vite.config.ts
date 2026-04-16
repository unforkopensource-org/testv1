import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The dashboard is shipped as static assets served by FastAPI at /. Vite
// builds into ../src/decibench/api/static/ so `pip install decibench && \
// decibench serve` works out of the box without needing Node at install time.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../src/decibench/api/static',
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
    rollupOptions: {
      output: {
        // Match what FastAPI mounts (`/assets`) so the built index.html refs
        // resolve correctly under both dev (`vite`) and prod (FastAPI) servers.
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to FastAPI during local development.
      '^/(runs|calls|call-evaluations|failure-inbox|health)': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
