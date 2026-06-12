import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  envDir: resolve(__dirname, '..'),
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler', // 使用现代 Sass API
        silenceDeprecations: ['legacy-js-api'], // 静默旧警告
      }
    }
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'es2022'
    },
    force: true,
    exclude: ['tree-sitter'],
  },
  build: {
    target: 'es2022',
    rollupOptions: {
      output: {
        manualChunks: {
          // 将大型 vendor 库独立拆分成 chunk，避免全都打进主 bundle
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          'echarts': ['echarts', 'vue-echarts'],
          'xlsx': ['xlsx'],
          'lodash': ['lodash-es'],
        },
      },
    },
    // 提升警告阈值到 1000KB，因为某些业务页面本身较大
    chunkSizeWarningLimit: 1000,
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    proxy: {
      '^/api/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/media/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/app-automation-templates/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/app-automation-reports/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/ws/': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', () => {})
          proxy.on('proxyReqWs', (proxyReq, req, socket) => {
            socket.on('error', () => {})
          })
        },
      },
    },
  },
  assetsInclude: ['**/*.wasm'],
})
