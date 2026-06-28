import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/** SessionsPage — User Process Flow §18.5 "Active Sessions". */
const S = { fontFamily: "'DM Sans', sans-serif" }

export default function SessionsPage() {
  const navigate = useNavigate()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)
  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }

  const load = () => client.get('/api/v1/auth/sessions/').then(r => setList(r.data?.results || r.data || [])).catch(() => setList([]))
  useEffect(() => { track('sessions.open', {}); load().finally(() => setLoading(false)) }, [])

  const revoke = async (s) => {
    if (!confirm('Terminar sessão neste dispositivo?')) return
    try {
      await client.delete(`/api/v1/auth/sessions/${s.id}/`)
      track('sessions.revoked', { session_id: s.id })
      await load()
      show('Sessão terminada.')
    } catch { show('Erro.', 'error') }
  }

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Sessões activas</h1>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 100px' }}>
        {loading ? <div style={{ height: 80, background: '#141414', borderRadius: 14 }} /> :
          list.length === 0 ? (
            <p style={{ ...S, fontSize: 13, color: '#9A9A9A', textAlign: 'center', padding: 24 }}>Sem sessões activas.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {list.map(s => (
                <div key={s.id} style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14 }}>
                  <p style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFF' }}>{s.device_name || s.user_agent?.slice(0, 50) || 'Dispositivo desconhecido'}</p>
                  <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>{s.ip_address || s.ip} · {s.location || ''}</p>
                  <p style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>Última actividade: {s.last_active_at ? new Date(s.last_active_at).toLocaleString('pt-AO') : '—'}</p>
                  <button onClick={() => revoke(s)}
                    style={{ marginTop: 10, padding: '8px 14px', borderRadius: 10, border: '1px solid rgba(220,38,38,0.3)', background: 'transparent', ...S, fontSize: 12, color: '#dc2626', cursor: 'pointer' }}>
                    Terminar sessão
                  </button>
                </div>
              ))}
            </div>
          )}
      </div>
    </BuyerLayout>
  )
}
