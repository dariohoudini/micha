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
