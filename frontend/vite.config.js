import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },

  server: {
    // ``host: true`` binds to 0.0.0.0 so phones on the same WiFi can
    // reach the dev server at http://<dev-machine-LAN-IP>:5173/.
    // Without this, Vite binds 127.0.0.1 and phones get connection
    // refused. See ops/PHONE_DEV.md for the full workflow.
    host: true,
    port: 5173,
    strictPort: false,
    proxy: {
      // Dev-only proxy: when phone hits 172.x.x.x:5173 the page
      // makes calls to "/api/..." (relative), Vite forwards to the
      // Django dev server on 127.0.0.1:8000.
      '/api':  { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws':   { target: 'ws://127.0.0.1:8001',   ws: true, changeOrigin: true },
      // Backend serves AASA + sitemap + robots at the root.
      '/.well-known': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },

  build: {
    rollupOptions: {
      output: {
        // Vite 8 (rolldown) requires manualChunks as a function
        manualChunks: (id) => {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) return 'vendor-react'
          if (id.includes('@tanstack/react-query')) return 'vendor-query'
          if (id.includes('react-hook-form') || id.includes('zod') || id.includes('@hookform')) return 'vendor-forms'
          if (id.includes('framer-motion')) return 'vendor-motion'
          if (id.includes('react-i18next') || id.includes('i18next')) return 'vendor-i18n'
          if (id.includes('node_modules/axios')) return 'vendor-axios'
          if (id.includes('node_modules/zustand')) return 'vendor-zustand'
        },
      },
    },
    chunkSizeWarningLimit: 600,
    minify: 'oxc',
    target: 'es2020',
  },

  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', 'axios', 'zustand', '@tanstack/react-query'],
  },
})