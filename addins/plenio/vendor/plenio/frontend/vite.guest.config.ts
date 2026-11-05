import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The party guests' song form: a page of its own, served by the guests' server below its token (``make/``) from
// plenio/player/guest_static - small, so a phone does not load the whole player. Relative paths: it works below
// any token, host and port.
export default defineConfig({
  root: fileURLToPath(new URL('./src/guest', import.meta.url)),
  base: './',
  plugins: [vue()],
  define: {
    __VUE_OPTIONS_API__: 'false',
    __VUE_PROD_DEVTOOLS__: 'false',
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false'
  },
  build: {
    outDir: fileURLToPath(new URL('../plenio/player/guest_static', import.meta.url)),
    emptyOutDir: true,
    target: 'es2022',
    minify: true,
    sourcemap: false,
    // the page's own scripts only (the guests' server allows nothing else): no inlined data: scripts
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/make-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]'
      }
    }
  }
})
