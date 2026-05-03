import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * useDebounce — delays updating a value until after delay ms
 * Use for search inputs to avoid firing API on every keystroke
 */
export function useDebounce(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

/**
 * useHaptic — triggers haptic feedback on supported devices
 * Works on iOS (via Capacitor) and Android
 */
export function useHaptic() {
  const trigger = useCallback(async (style = 'light') => {
    try {
      if (window.Capacitor?.isNativePlatform?.()) {
        const { Haptics, ImpactStyle } = await import('@capacitor/haptics')
        const styleMap = {
          light: ImpactStyle.Light,
          medium: ImpactStyle.Medium,
          heavy: ImpactStyle.Heavy,
        }
        await Haptics.impact({ style: styleMap[style] || ImpactStyle.Light })
      } else if (navigator.vibrate) {
        // Web fallback
        const durationMap = { light: 10, medium: 25, heavy: 50 }
        navigator.vibrate(durationMap[style] || 10)
      }
    } catch {}
  }, [])

  return { trigger }
}

/**
 * usePullToRefresh — pull down to refresh gesture
 */
export function usePullToRefresh(onRefresh, containerRef) {
  const [refreshing, setRefreshing] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)
  const startY = useRef(null)
  const THRESHOLD = 80

  useEffect(() => {
    const el = containerRef?.current
    if (!el) return

    const onTouchStart = (e) => {
      if (el.scrollTop === 0) startY.current = e.touches[0].clientY
    }

    const onTouchMove = (e) => {
      if (startY.current === null) return
      const dist = e.touches[0].clientY - startY.current
      if (dist > 0 && el.scrollTop === 0) {
        e.preventDefault()
        setPullDistance(Math.min(dist, THRESHOLD + 20))
      }
    }

    const onTouchEnd = async () => {
      if (pullDistance >= THRESHOLD && !refreshing) {
        setRefreshing(true)
        try { await onRefresh() } catch {}
        setRefreshing(false)
      }
      setPullDistance(0)
      startY.current = null
    }

    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd)

    return () => {
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
    }
  }, [onRefresh, pullDistance, refreshing])

  return { refreshing, pullDistance, threshold: THRESHOLD }
}

/**
 * useInfiniteScroll — triggers callback when user scrolls near bottom
 */
export function useInfiniteScroll(onLoadMore, { threshold = 200, enabled = true } = {}) {
  const containerRef = useRef(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el || !enabled) return

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el
      if (scrollHeight - scrollTop - clientHeight < threshold) {
        onLoadMore()
      }
    }

    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => el.removeEventListener('scroll', handleScroll)
  }, [onLoadMore, threshold, enabled])

  return { containerRef }
}

/**
 * useAndroidBackButton — handles hardware back button on Android
 */
export function useAndroidBackButton(onBack) {
  useEffect(() => {
    if (!window.Capacitor?.isNativePlatform?.()) return

    let cleanup = () => {}

    const setup = async () => {
      try {
        const { App } = await import('@capacitor/app')
        const { remove } = await App.addListener('backButton', onBack)
        cleanup = remove
      } catch {}
    }

    setup()
    return () => cleanup()
  }, [onBack])
}

/**
 * usePageTitle — sets document title for web version
 */
export function usePageTitle(title) {
  useEffect(() => {
    const prev = document.title
    document.title = title ? `${title} — MICHA Express` : 'MICHA Express'
    return () => { document.title = prev }
  }, [title])
}

export function usePrevious(value) {
  const ref = useRef()
  useEffect(() => { ref.current = value })
  return ref.current
}

export function useLocalStorage(key, defaultValue) {
  const [value, setValue] = useState(() => {
    try {
      const stored = localStorage.getItem(key)
      return stored ? JSON.parse(stored) : defaultValue
    } catch { return defaultValue }
  })

  const set = useCallback((newValue) => {
    setValue(newValue)
    try { localStorage.setItem(key, JSON.stringify(newValue)) } catch {}
  }, [key])

  return [value, set]
}

export function useCopyToClipboard() {
  const [copied, setCopied] = useState(false)

  const copy = useCallback(async (text) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const el = document.createElement('textarea')
      el.value = text
      el.style.cssText = 'position:fixed;left:-9999px'
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [])

  return { copy, copied }
}

export function useWebShare() {
  const canShare = typeof navigator !== 'undefined' && !!navigator.share

  const share = useCallback(async ({ title, text, url }) => {
    if (!canShare) {
      await navigator.clipboard.writeText(url || text || title || '')
      return 'copied'
    }
    try {
      await navigator.share({ title, text, url })
      return 'shared'
    } catch (err) {
      if (err.name !== 'AbortError') throw err
      return 'cancelled'
    }
  }, [canShare])

  return { share, canShare }
}

export function useScrollRestoration(key) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const saved = sessionStorage.getItem(`scroll:${key}`)
    if (saved) el.scrollTop = parseInt(saved, 10)
    const save = () => sessionStorage.setItem(`scroll:${key}`, el.scrollTop)
    el.addEventListener('scroll', save, { passive: true })
    return () => el.removeEventListener('scroll', save)
  }, [key])

  return ref
}

export function useIntersection(options = {}) {
  const [inView, setInView] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { threshold: 0.1, ...options }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return { ref, inView }
}

export function useCountdown(targetDate) {
  const [timeLeft, setTimeLeft] = useState(null)

  useEffect(() => {
    if (!targetDate) return
    const calc = () => {
      const diff = new Date(targetDate) - Date.now()
      if (diff <= 0) { setTimeLeft(null); return }
      const h = Math.floor(diff / 3600000)
      const m = Math.floor((diff % 3600000) / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setTimeLeft({ h, m, s, formatted: `${h}h ${String(m).padStart(2,'0')}m ${String(s).padStart(2,'0')}s` })
    }
    calc()
    const id = setInterval(calc, 1000)
    return () => clearInterval(id)
  }, [targetDate])

  return timeLeft
}
