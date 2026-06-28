import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'

// i18n must be imported before App
import '@/i18n/index.js'

import '@/styles/index.css'
import App from './App.jsx'
import { queryClient } from '@/lib/queryClient'
import { ToastProvider } from '@/components/ui/Toast'
// R1 Sprint 3: lazy Sentry init. No-op when VITE_SENTRY_DSN unset.
import { initSentry } from '@/lib/sentry'
initSentry()

// Tier 7: opportunistic service-worker registration. Caches hashed
// assets cache-first + SPA shell network-first. No-op in dev.
import { registerServiceWorker } from '@/lib/sw-register'
registerServiceWorker()

async function init() {
  // ── Capacitor native setup ─────────────────────────────────────────────
  if (window.Capacitor?.isNativePlatform?.()) {
    const [
      { SplashScreen },
      { StatusBar, Style },
      { Keyboard },
    ] = await Promise.all([
      import('@capacitor/splash-screen'),
      import('@capacitor/status-bar'),
      import('@capacitor/keyboard'),
    ])

    try {
      await StatusBar.setStyle({ style: Style.Dark })
      await StatusBar.setBackgroundColor({ color: '#0A0A0A' })
      await StatusBar.setOverlaysWebView({ overlay: true })
    } catch {}

    try {
      await Keyboard.setResizeMode({ mode: 'body' })
    } catch {}

    // Hide splash after first render
    setTimeout(async () => {
      try { await SplashScreen.hide({ fadeOutDuration: 300 }) } catch {}
    }, 500)
  }

  // ── Network listeners ──────────────────────────────────────────────────
  const { useUIStore } = await import('@/stores/uiStore')
  window.addEventListener('online', () => useUIStore.getState().setOnline(true))
  window.addEventListener('offline', () => useUIStore.getState().setOnline(false))

  // ── Auth store init ────────────────────────────────────────────────────
  const { useAuthStore } = await import('@/stores/authStore')
  useAuthStore.getState().init()

  // ── Mobile App Engineering stack (CH4/14/19/20/21/22/24) ──────────────
  // Each init is fire-and-forget and fail-open — a broken analytics or
  // experiments backend must never block app start.
  try {
    const { installCrashHandlers } = await import('@/lib/crashReport')
    installCrashHandlers()                       // CH19 crash ingest
  } catch {}
  import('@/lib/eventBatch')
    .then(({ initEventBatching }) => initEventBatching())  // CH20
    .catch(() => {})
  import('@/lib/syncQueue')
    .then(({ initSyncQueue }) => initSyncQueue())          // CH4
    .catch(() => {})
  import('@/lib/appState')
    .then(({ initAppState }) => initAppState())            // CH14
    .catch(() => {})
  import('@/lib/perfMetrics')
    .then(({ initPerfMetrics }) => initPerfMetrics())      // CH24 RUM
    .catch(() => {})
  import('@/lib/abClient')
    .then(({ initAB }) =>
      initAB(useAuthStore.getState().user?.id))            // CH21
    .catch(() => {})
  // CH22 deferred deep link — first-launch claim, then route.
  try {
    const FIRST_LAUNCH_KEY = 'micha_first_launch_done'
    if (!localStorage.getItem(FIRST_LAUNCH_KEY)) {
      localStorage.setItem(FIRST_LAUNCH_KEY, '1')
      const [{ default: client }] = await Promise.all([import('@/api/client')])
      client.post('/api/v1/mobile/deeplinks/claim/', {})
        .then(({ data }) => {
          if (data.found && data.target_path?.startsWith('/')) {
            window.history.replaceState(null, '', data.target_path)
          }
        })
        .catch(() => {})
    }
  } catch {}

  // ── Mount React ────────────────────────────────────────────────────────
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
        <ToastProvider />
        {import.meta.env.DEV && (
          <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" />
        )}
      </QueryClientProvider>
    </StrictMode>
  )
}

init()
