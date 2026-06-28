import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/** VouchersPage — User Process Flow §16.2. Lists collected coupons.
 *  Backed by `/api/v1/promotions/coupons/mine/` + collect endpoint. */
const S = { fontFamily: "'DM Sans', sans-serif" }

export default function VouchersPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('available')
  const [list, setList] = useState([])
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)

  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }
  const load = (s = tab) => client.get(`/api/v1/promotions/coupons/mine/?status=${s}`)
    .then(r => setList(r.data?.results || r.data || []))
    .catch(() => setList([]))

  useEffect(() => { track('vouchers.open', {}); load().finally(() => setLoading(false)) }, [])
  useEffect(() => { setLoading(true); load(tab).finally(() => setLoading(false)) }, [tab])

  const collect = async () => {
    if (!code.trim()) return
    try {
      await client.post('/api/v1/promotions/coupons/collect/', { code: code.trim() })
      track('vouchers.collected', { code: code.trim() })
      setCode('')
      await load()
      show('Cupão guardado!')
    } catch (err) {
      show(err.response?.data?.detail || 'Cupão inválido.', 'error')
    }
  }

  const copy = (c) => {
    try { navigator.clipboard?.writeText(c); track('vouchers.copy', { code: c }); show('Código copiado!') } catch {}
  }

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Cupões</h1>
      </div>

      <div style={{ padding: '8px 16px 12px' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <input value={code} onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="Insira código"
            style={{ flex: 1, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '11px 13px', ...S, fontSize: 13, color: '#FFF', outline: 'none' }} />
          <button onClick={collect} disabled={!code.trim()}
            style={{ padding: '0 18px', borderRadius: 12, border: 'none', background: code.trim() ? '#C9A84C' : '#2A2A2A', ...S, fontSize: 13, fontWeight: 700, color: code.trim() ? '#0A0A0A' : '#555', cursor: 'pointer' }}>
            Guardar
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid #1A1A1A', padding: '0 16px' }}>
        {[{ v: 'available', l: 'Disponíveis' }, { v: 'used', l: 'Usados' }, { v: 'expired', l: 'Expirados' }].map(t => (
          <button key={t.v} onClick={() => setTab(t.v)}
            style={{ flex: 1, padding: '12px 0', background: 'none', border: 'none', cursor: 'pointer', ...S, fontSize: 13, fontWeight: tab === t.v ? 700 : 400, color: tab === t.v ? '#C9A84C' : '#9A9A9A', borderBottom: `2px solid ${tab === t.v ? '#C9A84C' : 'transparent'}`, marginBottom: -1 }}>{t.l}</button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px 100px' }}>
        {loading ? <div style={{ height: 80, background: '#141414', borderRadius: 14 }} /> :
          list.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center' }}>
              <p style={{ fontSize: 40 }}>🎟️</p>
              <p style={{ ...S, fontSize: 13, color: '#9A9A9A', marginTop: 6 }}>Sem cupões {tab === 'available' ? 'disponíveis' : tab === 'used' ? 'usados' : 'expirados'}.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {list.map(c => (
                <div key={c.id} style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ ...S, fontSize: 18, fontWeight: 700, color: '#C9A84C' }}>
                      {c.discount_type === 'percentage' ? `${c.discount_value}%` : `${Number(c.discount_value).toLocaleString('pt-AO')} Kz`}
                    </p>
                    <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>Min. {Number(c.min_order_amount).toLocaleString('pt-AO')} Kz</p>
                    <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>
                      {c.valid_until ? `Expira ${new Date(c.valid_until).toLocaleDateString('pt-AO')}` : 'Sem expiração'}
                    </p>
                    <p style={{ ...S, fontSize: 11, color: '#FFF', marginTop: 6, fontFamily: 'monospace', letterSpacing: '0.05em' }}>{c.code}</p>
                  </div>
                  {tab === 'available' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <button onClick={() => { navigate('/cart'); track('vouchers.use_now', { code: c.code }) }}
                        style={{ padding: '8px 14px', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 11, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>Usar</button>
                      <button onClick={() => copy(c.code)}
                        style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 11, color: '#FFF', cursor: 'pointer' }}>Copiar</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
      </div>
    </BuyerLayout>
  )
}
