import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/** LoyaltyPage — User Process Flow §17.3. Buyer loyalty points
 *  balance + earn/redeem history. Backed by /api/v1/auth/loyalty/. */
const S = { fontFamily: "'DM Sans', sans-serif" }

export default function LoyaltyPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    track('loyalty.open', {})
    client.get('/api/v1/loyalty/me/')
      .then(r => setData(r.data))
      .catch(() => setData({ balance: 0, transactions: [] }))
      .finally(() => setLoading(false))
  }, [])

  return (
    <BuyerLayout>
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Pontos de fidelidade</h1>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 100px' }}>
        {loading ? <div style={{ height: 120, background: '#141414', borderRadius: 14 }} /> : (
          <>
            <div style={{ background: 'linear-gradient(135deg, rgba(201,168,76,0.18), rgba(201,168,76,0.04))', border: '1px solid rgba(201,168,76,0.3)', borderRadius: 16, padding: 22, textAlign: 'center' }}>
              <p style={{ ...S, fontSize: 12, color: '#BFBFBF', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Saldo</p>
              <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 38, fontWeight: 700, color: '#C9A84C' }}>{data?.balance ?? 0}</p>
              <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 4 }}>pontos · 100 pts = 50 Kz no checkout</p>
            </div>
            <div style={{ marginTop: 20 }}>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Histórico</p>
              {(data?.transactions || []).length === 0 ? (
                <p style={{ ...S, fontSize: 13, color: '#9A9A9A', padding: 12 }}>Sem movimentos.</p>
              ) : (
                (data.transactions).map((t, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #1A1A1A' }}>
                    <div>
                      <p style={{ ...S, fontSize: 13, color: '#FFF' }}>{t.description || t.type}</p>
                      <p style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>{new Date(t.created_at || t.timestamp).toLocaleDateString('pt-AO')}</p>
                    </div>
                    <p style={{ ...S, fontSize: 14, fontWeight: 700, color: t.amount > 0 ? '#10b981' : '#ef4444' }}>{t.amount > 0 ? '+' : ''}{t.amount}</p>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </BuyerLayout>
  )
}
