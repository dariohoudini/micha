import { useState, useEffect, useCallback } from 'react'

/**
 * useNetworkStatus — detects online/offline state
 * Usage: const { isOnline } = useNetworkStatus()
 */
export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return { isOnline }
}

/**
 * useApi — wraps API calls with loading/error/retry state
 * Usage:
 *   const { data, loading, error, execute } = useApi(productsAPI.getFeed)
 *   useEffect(() => { execute() }, [])
 */
export function useApi(apiFn) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const execute = useCallback(async (...args) => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiFn(...args)
      setData(response.data)
      return response.data
    } catch (err) {
      if (!navigator.onLine) {
        setError('Sem ligação à internet. Verifique a sua rede.')
      } else {
        const message =
          err.response?.data?.detail ||
          err.response?.data?.message ||
          'Ocorreu um erro. Tente novamente.'
        setError(message)
      }
      throw err
    } finally {
      setLoading(false)
    }
  }, [apiFn])

  const reset = () => { setData(null); setError(null) }

  return { data, loading, error, execute, reset }
}

/**
 * OfflineBanner — shows a banner when the user is offline
 * Place this inside your layout components
 */
export function OfflineBanner() {
  const { isOnline } = useNetworkStatus()

  if (isOnline) return null

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999,
      background: '#dc2626', padding: '10px 16px',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="1" y1="1" x2="23" y2="23" />
        <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55M5 12.55a10.94 10.94 0 0 1 5.17-2.39M10.71 5.05A16 16 0 0 1 22.56 9M1.42 9a15.91 15.91 0 0 1 4.7-2.88M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>
        Sem ligação à internet
      </span>
    </div>
  )
}
