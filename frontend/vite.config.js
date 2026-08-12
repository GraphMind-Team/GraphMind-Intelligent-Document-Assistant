import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Vite itself ignores `test` -- Vitest reads it from this same config
  // (no separate vitest.config.js) so dev/build/test all share one set of
  // plugins/aliases instead of three configs drifting apart.
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js'],
    globals: true,
  },
})
