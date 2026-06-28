import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * SellerBusinessAdvisorPage — /seller/business-advisor
 *
 * AliExpress Complete 2025 CH 23.1 — Business Advisor module.
 *
 * Surfaces the metrics the doc lists: GMV, orders, conversion,
 * views, add-to-cart, dispute rate, on-time shipping, feedback,
 * avg response time. Backed by existing
 * /api/v1/analytics/seller/dashboard/ which already returns this
 * shape (built earlier in this codebase).
 *
 * Filter chips for date range. Traffic-source breakdown bar chart
 * rendered with a minimal inline SVG (no chart library).
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const RANGES = [
  { v: 'today', l: 'Hoje' },
  { v: '7',     l: '7 dias' },
  { v: '30',    l: '30 dias' },
  { v: '90',    l: '90 dias' },
]

function MetricCard({ label, value, sub, accent = '#C9A84C' }) {
  return (
    <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14 }}>
      <p style={{ ...S, fontSize: 10, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</p>
      <p style={{ ...S, fontSize: 22, fontWeight: 700, color: accent, marginTop: 4 }}>{value}</p>
      {sub && <p style={{ ...S, fontSize: 10, color: '#9A9A9A', marginTop: 2 }}>{sub}</p>}
    </div>
  )
}

export default function SellerBusinessAdvisorPage() {
  const navigate = useNavigate()
  const [range, setRange] = useState('30')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    track('seller.advisor.open', { range })
    setLoading(true)
    client.get(`/api/v1/analytics/seller/dashboard/?days=${range === 'today' ? 1 : range}`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [range])

  const total = (data?.traffic_sources || []).reduce((s, x) => s + (x.visits || 0), 0) || 1
  return (
    <SellerLayout title="Business Advisor" showBack>
      <div style={{ padding: '8px 16px 12px', display: 'flex', gap: 6, overflowX: 'auto' }}>
        {RANGES.map(r => (
          <button key={r.v} onClick={() => setRange(r.v)}
            style={{ padding: '7px 14px', borderRadius: 18, border: `1.5px solid ${range === r.v ? '#C9A84C' : '#2A2A2A'}`, background: range === r.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: range === r.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}>{r.l}</button>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 100px' }}>
        {loading ? <div style={{ height: 200, background: '#141414', borderRadius: 14 }} /> : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
              <MetricCard label="GMV" value={`${Number(data?.totals?.gmv || 0).toLocaleString('pt-AO')} Kz`} sub={data?.totals?.gmv_change ? `${data.totals.gmv_change > 0 ? '↑' : '↓'} ${Math.abs(data.totals.gmv_change)}%` : null} />
              <MetricCard label="Pedidos" value={data?.totals?.orders ?? 0} />
              <MetricCard label="Conversão" value={`${(data?.totals?.conversion_rate || 0).toFixed(1)}%`} accent="#10b981" />
              <MetricCard label="Vistas" value={Number(data?.totals?.views || 0).toLocaleString('pt-AO')} />
              <MetricCard label="Disputas" value={`${(data?.totals?.dispute_rate || 0).toFixed(1)}%`} accent={(data?.totals?.dispute_rate || 0) > 2 ? '#ef4444' : '#10b981'} />
              <MetricCard label="On-time" value={`${(data?.totals?.on_time_shipping || 0).toFixed(1)}%`} accent={(data?.totals?.on_time_shipping || 0) >= 95 ? '#10b981' : '#f59e0b'} />
              <MetricCard label="Feedback" value={`${(data?.totals?.feedback_score || 0).toFixed(1)}%`} />
              <MetricCard label="Resposta avg" value={`${(data?.totals?.avg_response_hours || 0).toFixed(1)}h`} />
            </div>

            {/* Traffic source breakdown */}
            {(data?.traffic_sources || []).length > 0 && (
              <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14, marginBottom: 14 }}>
                <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>Fontes de tráfego</p>
                {data.traffic_sources.map(s => {
                  const pct = Math.round(((s.visits || 0) / total) * 100)
                  return (
                    <div key={s.source} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ ...S, fontSize: 12, color: '#FFF' }}>{s.source}</span>
                        <span style={{ ...S, fontSize: 12, color: '#C9A84C' }}>{pct}% · {s.visits}</span>
                      </div>
                      <div style={{ height: 6, background: '#1E1E1E', borderRadius: 3, marginTop: 4 }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: '#C9A84C', borderRadius: 3 }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Top products */}
            {(data?.top_products || []).length > 0 && (
              <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14 }}>
                <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Top produtos</p>
                {data.top_products.slice(0, 5).map((p, i) => (
                  <div key={p.id || i} onClick={() => navigate(`/seller/products/${p.id}/edit`)} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #1E1E1E', cursor: 'pointer' }}>
                    <span style={{ ...S, fontSize: 13, color: '#FFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60%' }}>{p.title}</span>
                    <span style={{ ...S, fontSize: 12, color: '#C9A84C', fontWeight: 700 }}>{Number(p.revenue || 0).toLocaleString('pt-AO')} Kz</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </SellerLayout>
  )
}
