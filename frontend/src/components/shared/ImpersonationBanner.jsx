import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * Admin User Management CH17 — the constant impersonation indicator.
 * A fixed banner shown whenever an operator is viewing-as a user, so
 * they always know they're impersonating (no accidental action as the
 * user) and can exit in one tap. Also listens for the token-expiry
 * event the API client fires and exits cleanly.
 */
export default function ImpersonationBanner() {
  const navigate = useNavigate()
  const impersonating = useAuthStore(s => s.impersonating)
  const exitImpersonation = useAuthStore(s => s.exitImpersonation)

  useEffect(() => {
    const onExpired = async () => { await exitImpersonation(); navigate('/admin/users') }
    window.addEventListener('micha:impersonation-expired', onExpired)
    return () => window.removeEventListener('micha:impersonation-expired', onExpired)
  }, [exitImpersonation, navigate])

  if (!impersonating) return null

  const leave = async () => { await exitImpersonation(); navigate('/admin/users') }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 10000,
      background: '#7C3AED', color: '#fff', padding: '8px 14px',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      fontFamily: "'DM Sans', sans-serif", fontSize: 13,
      paddingTop: 'max(8px, env(safe-area-inset-top))',
    }}>
      <span>👁️ A ver como <strong>{impersonating.email}</strong> · acções sensíveis bloqueadas</span>
      <button onClick={leave} style={{
        background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff',
        borderRadius: 8, padding: '4px 12px', fontSize: 12, fontWeight: 700,
        cursor: 'pointer', flexShrink: 0,
      }}>Sair</button>
    </div>
  )
}
