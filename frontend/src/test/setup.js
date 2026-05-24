/**
 * Vitest setup — runs once before the test suite.
 *
 * Stubs in this file:
 *  • localStorage / sessionStorage — jsdom provides these but tests
 *    that import zustand persist() with createJSONStorage need them
 *    fully behaved.
 *  • matchMedia — Tailwind responsive helpers + framer-motion query it.
 *  • IntersectionObserver — react-intersection-observer would crash.
 */
import '@testing-library/jest-dom'

// matchMedia — return false for all media queries (mobile-first
// renders are the default in tests).
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })
}

// IntersectionObserver — minimal noop stub.
if (typeof window !== 'undefined' && !window.IntersectionObserver) {
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return [] }
  }
  window.IntersectionObserver = IntersectionObserverStub
}

// Capacitor — when a test imports something that touches Capacitor,
// stub to non-native so isNativePlatform() === false.
if (typeof window !== 'undefined' && !window.Capacitor) {
  window.Capacitor = {
    isNativePlatform: () => false,
    getPlatform: () => 'web',
  }
}
