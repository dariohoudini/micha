import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/** FlashSalePage — User Process Flow §16.3. Live flash sales grid. */
const S = { fontFamily: "'DM Sans', sans-serif" }

function Countdown({ end }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const ms = Math.max(0, new Date(end).getTime() - now)
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{String(h).padStart(2, '0')}:{String(m).padStart(2, '0')}:{String(s).padStart(2, '0')}</span>
}

export default function FlashSalePage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    track('flash_sale.open', {})
    client.get('/api/v1/promotions/flash-sales/')
      .then(r => setItems(r.data?.results || r.data || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  const earliest = items.length ? items.reduce((min, x) => new Date(x.end_time) < new Date(min) ? x.end_time : min, items[0].end_time) : null

  return (
    <BuyerLayout>
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>⚡ Promoções Flash</h1>
      </div>
      {earliest && (
        <div style={{ margin: '0 16px 12px', padding: 12, background: 'linear-gradient(135deg, rgba(239,68,68,0.18), rgba(239,68,68,0.04))', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 12, textAlign: 'center' }}>
          <p style={{ ...S, fontSize: 11, color: '#FFF', marginBottom: 4 }}>Termina em</p>
          <p style={{ ...S, fontSize: 22, color: '#ef4444' }}><Countdown end={earliest} /></p>
        </div>
      )}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 100px' }}>
        {loading ? <div style={{ height: 200, background: '#141414', borderRadius: 14 }} /> :
          items.length === 0 ? (
            <p style={{ ...S, fontSize: 14, color: '#9A9A9A', textAlign: 'center', padding: 32 }}>Sem promoções flash agora. Volte mais tarde!</p>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {items.map(f => {
                const sold = f.sold_count || 0
                const quota = f.quota || sold || 1
                const pct = Math.min(100, Math.round((sold / quota) * 100))
                return (
                  <button key={f.id} onClick={() => { navigate(`/product/${f.product_id}`); track('flash_sale.product_tap', { product_id: f.product_id }) }}
                    style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, overflow: 'hidden', cursor: 'pointer', textAlign: 'left', padding: 0 }}>
                    <div style={{ height: 140, background: '#1E1E1E' }}>
                      {f.product_thumbnail && <img src={f.product_thumbnail} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                    </div>
                    <div style={{ padding: 10 }}>
                      <p style={{ ...S, fontSize: 12, color: '#FFF', height: 32, overflow: 'hidden' }}>{f.product_title}</p>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
                        <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#ef4444' }}>{Number(f.sale_price).toLocaleString('pt-AO')}</span>
                        <span style={{ ...S, fontSize: 10, color: '#9A9A9A', textDecoration: 'line-through' }}>{Number(f.original_price).toLocaleString('pt-AO')}</span>
                      </div>
                      <div style={{ marginTop: 6, height: 4, background: '#1E1E1E', borderRadius: 2 }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: '#ef4444', borderRadius: 2 }} />
                      </div>
                      <p style={{ ...S, fontSize: 9, color: '#9A9A9A', marginTop: 2 }}>{pct}% vendido</p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
      </div>
    </BuyerLayout>
  )
}
