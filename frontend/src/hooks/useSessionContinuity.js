/**
 * MICHA Hyper-Personalization — Session Continuity
 * Remembers what user was doing and resumes seamlessly
 */
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

const SESSION_KEY = 'micha_last_session'

export function useSaveSession() {
  const location = useLocation()

  useEffect(() => {
    const skip = ['/', '/login', '/register', '/splash', '/language', '/welcome']
    if (!skip.includes(location.pathname)) {
      try {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({
          path: location.pathname,
          search: location.search,
          timestamp: Date.now(),
        }))
      } catch {}
    }
  }, [location])
}

export function useRestoreSession() {
  const navigate = useNavigate()

  const restore = () => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null')
      if (saved) {
        const age = Date.now() - saved.timestamp
        // Only restore if session is less than 30 minutes old
        if (age < 30 * 60 * 1000) {
          navigate(saved.path + (saved.search || ''), { replace: true })
          return true
        }
      }
    } catch {}
    return false
  }

  return restore
}

export function useLastSearchRestore() {
  const navigate = useNavigate()

  useEffect(() => {
    try {
      const lastSearch = localStorage.getItem('micha_last_search')
      if (lastSearch) {
        // Show last search as pre-filled suggestion (not auto-navigate)
        window.dispatchEvent(new CustomEvent('micha:last-search', {
          detail: { query: lastSearch }
        }))
      }
    } catch {}
  }, [])
}
