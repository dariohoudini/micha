/**
 * Vitest configuration (R1 Sprint 3).
 *
 * Why a separate file
 * ───────────────────
 * Vite-mode and Vitest-mode share the same plugin pipeline but
 * Vitest needs its own ``test`` block. Keeping the test config in a
 * sibling file makes ``npm test`` self-contained and avoids polluting
 * the production build config with test-only settings.
 *
 * Operator setup
 * ──────────────
 * Vitest itself isn't in package.json yet — operator runs:
 *   npm i -D vitest @vitest/coverage-v8 jsdom @testing-library/react @testing-library/jest-dom
 *
 * Until that's done, ``npm test`` will fail with a clear error
 * pointing here. Adding the dep set is a >100MB install — left as
 * an operator decision so CI image size doesn't grow silently.
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx,ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{js,jsx,ts,tsx}'],
      exclude: [
        'src/**/*.test.{js,jsx,ts,tsx}',
        'src/test/**',
        'src/**/*.config.js',
      ],
    },
  },
})
