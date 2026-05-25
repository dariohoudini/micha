/**
 * MICHA Express — UX Utility Hooks
 * Fixes: #2 swipe back, #6 pull to refresh, #7 scroll restore,
 *        #13/#37 haptics, #30 offline detection
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

// ─── Haptic feedback ─────────────────────────────────────────────
// Tier 6: prefer Capacitor Haptics on native (iOS Taptic Engine /
// Android system vibrator). Falls back to navigator.vibrate on web.
// All calls are fire-and-forget — never throw, never block.
let _capHaptics = null
let _capCheckStarted = false

function _ensureCapHaptics() {
  if (_capCheckStarted) return
  _capCheckStarted = true
  try {
    const isNative = (typeof window !== 'undefined'
      && window.Capacitor?.isNativePlatform?.())
    if (!isNative) return
    import('@capacitor/haptics')
      .then((mod) => { _capHaptics = mod })
      .catch(() => {})
  } catch {}
}

function _vibrate(pattern) {
  try { navigator.vibrate?.(pattern) } catch {}
}

function _notify(type, pattern) {
  _ensureCapHaptics()
  if (_capHaptics?.Haptics?.notification) {
    _capHaptics.Haptics.notification({ type }).catch(() => {})
  }
  _vibrate(pattern)
}

function _impact(style, pattern) {
  _ensureCapHaptics()
  if (_capHaptics?.Haptics?.impact) {
    _capHaptics.Haptics.impact({ style }).catch(() => {})
  }
  _vibrate(pattern)
}

export const haptic = {
  success:   () => _notify('SUCCESS', [50]),
  error:     () => _notify('ERROR',   [100, 50, 100]),
  warning:   () => _notify('WARNING', [60, 30, 60]),
  tap:       () => _impact('LIGHT',   [20]),
  light:     () => _impact('LIGHT',   [20]),
  medium:    () => _impact('MEDIUM',  [40]),
  heavy:     () => _impact('HEAVY',   [80]),
  selection: () => {
    _ensureCapHaptics()
    if (_capHaptics?.Haptics?.selectionChanged) {
      _capHaptics.Haptics.selectionChanged().catch(() => {})
    }
    _vibrate([10])
  },
}

// ─── Swipe back gesture (#2) ─────────────────────────────────────
export function useSwipeBack() {
  const navigate = useNavigate()
  useEffect(() => {
    let startX = 0
    let startY = 0
    const onStart = (e) => {
      startX = e.touches[0].clientX
      startY = e.touches[0].clientY
    }
    const onEnd = (e) => {
      const dx = e.changedTouches[0].clientX - startX
      const dy = Math.abs(e.changedTouches[0].clientY - startY)
      if (startX < 30 && dx > 80 && dy < 60) navigate(-1)
    }
    document.addEventListener('touchstart', onStart, { passive: true })
    document.addEventListener('touchend', onEnd, { passive: true })
    return () => {
      document.removeEventListener('touchstart', onStart)
      document.removeEventListener('touchend', onEnd)
    }
  }, [navigate])
}

// ─── Pull to refresh (#6) ────────────────────────────────────────
export function usePullToRefresh(onRefresh) {
  const [refreshing, setRefreshing] = useState(false)
  const [pullY, setPullY] = useState(0)
  const startY = useRef(0)

  useEffect(() => {
    const THRESHOLD = 70
    const onStart = (e) => { startY.current = e.touches[0].clientY }
    const onMove = (e) => {
      if (window.scrollY > 0) return
      const dy = e.touches[0].clientY - startY.current
      if (dy > 0) setPullY(Math.min(dy, THRESHOLD + 20))
    }
    const onEnd = async () => {
      if (pullY >= THRESHOLD) {
        setRefreshing(true)
        haptic.success()
        await onRefresh?.()
        setRefreshing(false)
      }
      setPullY(0)
    }
    document.addEventListener('touchstart', onStart, { passive: true })
    document.addEventListener('touchmove', onMove, { passive: true })
    document.addEventListener('touchend', onEnd)
    return () => {
      document.removeEventListener('touchstart', onStart)
      document.removeEventListener('touchmove', onMove)
      document.removeEventListener('touchend', onEnd)
    }
  }, [pullY, onRefresh])

  return { pullY, refreshing }
}

// ─── Scroll position restore (#7) ────────────────────────────────
export function useScrollRestore(key) {
  const ref = useRef(null)
  useEffect(() => {
    const saved = sessionStorage.getItem(`scroll_${key}`)
    if (saved && ref.current) ref.current.scrollTop = parseInt(saved)
    return () => {
      if (ref.current) sessionStorage.setItem(`scroll_${key}`, ref.current.scrollTop)
    }
  }, [key])
  return ref
}

// ─── Infinite scroll (#9) ────────────────────────────────────────
export function useInfiniteScroll(loadMore, hasMore) {
  const sentinelRef = useRef(null)
  useEffect(() => {
    if (!hasMore) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) loadMore() },
      { threshold: 0.1 }
    )
    if (sentinelRef.current) observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [loadMore, hasMore])
  return sentinelRef
}

// ─── Keyboard visibility (#4) ────────────────────────────────────
export function useKeyboardVisible() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const handler = () => setVisible(vv.height < window.innerHeight * 0.75)
    vv.addEventListener('resize', handler)
    return () => vv.removeEventListener('resize', handler)
  }, [])
  return visible
}

// ─── Offline detection (#30) ─────────────────────────────────────
export function useOffline() {
  const [offline, setOffline] = useState(!navigator.onLine)
  useEffect(() => {
    const on = () => setOffline(false)
    const off = () => setOffline(true)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off) }
  }, [])
  return offline
}

// ─── Swipe to delete (#15, #27) ──────────────────────────────────
export function useSwipeToDelete(onDelete) {
  const [swipeX, setSwipeX] = useState(0)
  const startX = useRef(0)
  const handlers = {
    onTouchStart: (e) => { startX.current = e.touches[0].clientX },
    onTouchMove: (e) => {
      const dx = e.touches[0].clientX - startX.current
      if (dx < 0) setSwipeX(Math.max(dx, -100))
    },
    onTouchEnd: () => {
      if (swipeX < -80) { haptic.error(); onDelete?.() }
      else setSwipeX(0)
    },
  }
  return { swipeX, handlers }
}
