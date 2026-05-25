/**
 * SellerDashboardR7Page
 * ──────────────────────
 * Consumes the R7 backend:
 *   GET /api/v1/analytics/seller/dashboard/?days=7|30|90|365
 *
 * One round-trip serves the entire dashboard.
 */
import { useEffect, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell,
} from 'recharts'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'


function fmtKz(n) {
  const v = Number(n) || 0
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
  return v.toFixed(0)
}


function StatCard({ label, value, sub }) {
  return (
    <div style={{
      background: ADMIN_COLORS.card,
      border: `1px solid ${ADMIN_COLORS.border}`,
      borderRadius: 12, padding: 14, flex: '1 1 140px',
    }}>
      <div style={{ fontSize: 11, color: ADMIN_COLORS.muted,
                    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: ADMIN_COLORS.text }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginTop: 4 }}>
          {sub}
        </div>
      )}
    </div>
  )
}


export default function SellerDashboardR7Page() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError('')
    client.get('/api/v1/analytics/seller/dashboard/', { params: { days } })
      .then(r => setData(r.data))
      .catch(e => setError(e?.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [days])

  return (
    <AdminLayout title="Analytics">
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {[7, 30, 90, 365].map(d => (
            <button key={d}
                    onClick={() => setDays(d)}
                    style={{
                      background: days === d ? '#6366F1' : 'transparent',
                      color: days === d ? 'white' : ADMIN_COLORS.text,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      padding: '6px 14px', borderRadius: 6,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    }}>{d}d</button>
          ))}
        </div>

        {loading ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20 }}>Loading…</div>
        ) : error ? (
          <div style={{
            background: 'rgba(239,68,68,0.1)', color: '#F87171',
            padding: 12, borderRadius: 8,
          }}>{error}</div>
        ) : data && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap',
                          marginBottom: 16 }}>
              <StatCard label="Gross Revenue"
                        value={`${fmtKz(data.totals.gross_revenue)} Kz`}
                        sub={`${data.totals.order_count} orders`} />
              <StatCard label="Net Revenue"
                        value={`${fmtKz(data.totals.net_revenue)} Kz`}
                        sub={`${fmtKz(data.totals.refunded)} Kz refunded`} />
              <StatCard label="Avg Order Value"
                        value={`${fmtKz(data.totals.avg_order_value)} Kz`} />
              <StatCard label="Repeat Rate"
                        value={`${data.repeat_rate.rate_pct}%`}
                        sub={`${data.repeat_rate.repeat_buyers}/${data.repeat_rate.total_buyers} buyers`} />
            </div>

            <Section title="Revenue (daily)">
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data.revenue}>
                    <defs>
                      <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#6366F1" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#6366F1" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={ADMIN_COLORS.border} />
                    <XAxis dataKey="day" stroke={ADMIN_COLORS.muted}
                           tick={{ fontSize: 10 }}
                           tickFormatter={(d) => d.slice(5)} />
                    <YAxis stroke={ADMIN_COLORS.muted}
                           tick={{ fontSize: 10 }}
                           tickFormatter={(v) => fmtKz(v)} />
                    <Tooltip
                      contentStyle={{
                        background: ADMIN_COLORS.card,
                        border: `1px solid ${ADMIN_COLORS.border}`,
                        borderRadius: 8, fontSize: 12,
                      }}
                      formatter={(v) => `${fmtKz(v)} Kz`} />
                    <Area type="monotone" dataKey="revenue"
                          stroke="#6366F1" strokeWidth={2}
                          fill="url(#rev)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Section>

            <Section title="Funnel">
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={[
                    { stage: 'View', n: data.funnel.counts.view },
                    { stage: 'Cart', n: data.funnel.counts.add_cart },
                    { stage: 'Checkout', n: data.funnel.counts.checkout },
                    { stage: 'Purchase', n: data.funnel.counts.purchase },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" stroke={ADMIN_COLORS.border} />
                    <XAxis dataKey="stage" stroke={ADMIN_COLORS.muted}
                           tick={{ fontSize: 11 }} />
                    <YAxis stroke={ADMIN_COLORS.muted} tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={{
                      background: ADMIN_COLORS.card,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      borderRadius: 8, fontSize: 12,
                    }} />
                    <Bar dataKey="n" fill="#6366F1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{
                marginTop: 8, fontSize: 12, color: ADMIN_COLORS.muted,
              }}>
                View → purchase: {data.funnel.view_to_purchase_pct}%
              </div>
            </Section>

            <Section title="Top Products by Revenue">
              {(data.top_products?.by_revenue || []).length === 0 ? (
                <div style={{ color: ADMIN_COLORS.muted, padding: 8 }}>No sales yet.</div>
              ) : data.top_products.by_revenue.map(p => (
                <div key={p.product_id} style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '6px 0', borderBottom: `1px solid ${ADMIN_COLORS.border}`,
                  fontSize: 13,
                }}>
                  <span style={{ color: ADMIN_COLORS.text }}>{p.title}</span>
                  <span style={{ color: ADMIN_COLORS.muted }}>
                    {fmtKz(p.revenue)} Kz · {p.units} un
                  </span>
                </div>
              ))}
            </Section>

            <Section title="Top Cities">
              {data.geo.length === 0 ? (
                <div style={{ color: ADMIN_COLORS.muted, padding: 8 }}>No regional data.</div>
              ) : data.geo.map(g => (
                <div key={g.city} style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '6px 0', borderBottom: `1px solid ${ADMIN_COLORS.border}`,
                  fontSize: 13,
                }}>
                  <span style={{ color: ADMIN_COLORS.text }}>{g.city}</span>
                  <span style={{ color: ADMIN_COLORS.muted }}>
                    {fmtKz(g.revenue)} Kz · {g.orders} orders
                  </span>
                </div>
              ))}
            </Section>
          </>
        )}
      </div>
    </AdminLayout>
  )
}


function Section({ title, children }) {
  return (
    <div style={{
      background: ADMIN_COLORS.card,
      border: `1px solid ${ADMIN_COLORS.border}`,
      borderRadius: 12, padding: 14, marginBottom: 12,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: ADMIN_COLORS.text,
                    marginBottom: 10 }}>
        {title}
      </div>
      {children}
    </div>
  )
}
