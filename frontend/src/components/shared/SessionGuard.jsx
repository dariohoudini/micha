import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * SessionGuard — AliExpress Process Flow §19 (Session & Timeout).
 *
 * Responsibilities:
 *   §19.1  Idle warning at 25 min — modal "Session will expire in 5
 *          minutes. Stay logged in?"
 *   §19.2  Session expiry at 30 min — when the *next* auth API call
 *          comes back 401 the existing axios interceptor handles
 *          refresh-or-redirect; we surface a modal here too in case
 *          the user just left the app open with no activity.
 *   §19.3  beforeunload — handled at the browser level when an
 *          unsaved form sets ``window.__michaUnsaved = true`` (the
 *          product wizard sets it whenever the form is non-empty).
 *
 * Mount once near the top of the app tree (next to <GlobalSetup/>).
 */

const IDLE_WARN_MS    = 25 * 60 * 1000  // 25 min — show warning
const IDLE_EXPIRE_MS  = 30 * 60 * 1000  // 30 min — force logout
const S = { fontFamily: "'DM Sans', sans-serif" }

export default function SessionGuard() {
  const navigate = useNavigate()
  const isAuth = useAuthStore(s => s.isAuth)
  const logout = useAuthStore(s => s.logout)
  const [warning, setWarning] = useState(false)
  const [expired, setExpired] = useState(false)
  const lastActivity = useRef(Date.now())
  const warnTimer = useRef(null)
  const expTimer  = useRef(null)
  const countdown = useRef(null)
  const [secondsLeft, setSecondsLeft] = useState(300)

  // ── Reset idle timer on user activity ──────────────────────────
  useEffect(() => {
    if (!isAuth) return
    const reset = () => {
      lastActivity.current = Date.now()
      if (warning) setWarning(false)
      clearTimeout(warnTimer.current); clearTimeout(expTimer.current); clearInterval(countdown.current)
      warnTimer.current = setTimeout(() => {
        setWarning(true)
        setSecondsLeft(Math.floor((IDLE_EXPIRE_MS - IDLE_WARN_MS) / 1000))
        countdown.current = setInterval(() => setSecondsLeft(x => Math.max(0, x - 1)), 1000)
      }, IDLE_WARN_MS)
      expTimer.current = setTimeout(async () => {
        clearInterval(countdown.current)
        setWarning(false)
        setExpired(true)
        // best-effort logout — clears tokens + per-device flags
        try { await logout() } catch {}
      }, IDLE_EXPIRE_MS)
    }
    const events = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll']
    events.forEach(e => window.addEventListener(e, reset, { passive: true }))
    reset()
    return () => {
      events.forEach(e => window.removeEventListener(e, reset))
      clearTimeout(warnTimer.current); clearTimeout(expTimer.current); clearInterval(countdown.current)
    }
  }, [isAuth, logout, warning])

  // ── §19.3 beforeunload guard for unsaved forms ─────────────────
  useEffect(() => {
    const onUnload = (e) => {
      if (window.__michaUnsaved) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])

  if (!warning && !expired) return null

  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
      zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }}>
      <div style={{ background: '#141414', border: '1px solid #2A2A2A', borderRadius: 16, padding: 22, maxWidth: 360, width: '100%' }}>
        {expired ? (
          <>
            <p style={{ ...S, fontSize: 16, fontWeight: 700, color: '#FFFFFF', marginBottom: 6 }}>Sessão expirada</p>
            <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 16 }}>
              A sua sessão expirou por inactividade. Volte a iniciar sessão para continuar.
            </p>
            <button onClick={() => { setExpired(false); navigate('/login') }}
              style={{ width: '100%', padding: '12px 0', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
              Iniciar sessão
            </button>
          </>
        ) : (
          <>
            <p style={{ ...S, fontSize: 16, fontWeight: 700, color: '#FFFFFF', marginBottom: 6 }}>Continua aí?</p>
            <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 4 }}>
              A sua sessão vai expirar em
            </p>
            <p style={{ ...S, fontSize: 28, fontWeight: 700, color: '#C9A84C', marginBottom: 16 }}>{fmt(secondsLeft)}</p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={async () => { try { await logout() } catch {}; navigate('/login') }}
                style={{ flex: 1, padding: '12px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 13, color: '#FFFFFF', cursor: 'pointer' }}>
                Terminar sessão
              </button>
              <button onClick={() => { lastActivity.current = Date.now(); setWarning(false) }}
                style={{ flex: 1, padding: '12px 0', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                Continuar
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
