import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.')
  // Optional dev proxy: if VITE_API_BASE_URL is left empty (relative mode), `/api/*`
  // is forwarded to VITE_API_PROXY_TARGET (default http://localhost:8000). Avoids CORS locally.
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
  const srcDir = decodeURIComponent(new URL('./src', import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, '$1')

  return {
    plugins: [vue()],
    resolve: {
      alias: { '@': srcDir },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
      },
    },
    build: {
      chunkSizeWarningLimit: 900,
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: 'chartjs', test: /node_modules[\\/]chart\.js/, priority: 2 },
              { name: 'mock-outcomes', test: /services[\\/]mock[\\/]replayOutcomes/, priority: 2 },
              { name: 'mock-data', test: /services[\\/]mock[\\/]/, priority: 1 },
            ],
          },
        },
      },
    },
  }
})
