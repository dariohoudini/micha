/**
 * SellerDashboardR7Page — production polish pass.
 */
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from 'recharts'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import { DashboardSkeleton } from '@/components/ui/AdminSkeletons'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import { useApiQuery } from '@/hooks/useApiKit'
import { useState } from 'react'


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


function Section({ title, children, empty }) {
  return (
    <section aria-label={title} style={{
      background: ADMIN_COLORS.card,
      border: `1px solid ${ADMIN_COLORS.border}`,
      borderRadius: 12, padding: 14, marginBottom: 12,
    }}>
      <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700,
                   color: ADMIN_COLORS.text, marginBottom: 10 }}>
        {title}
      </h3>
      {empty ? (
        <div style={{ color: ADMIN_COLORS.muted, padding: 8, fontSize: 13 }}>
          {empty}
        </div>
      ) : children}
    </section>
  )
}


export default function SellerDashboardR7Page() {
  const [days, setDays] = useState(30)
  const query = useApiQuery('/api/v1/analytics/seller/dashboard/', { days })

  return (
    <AdminLayout title="Analytics">
      <div style={{ padding: 16 }}>
        <div role="tablist" aria-label="Time window"
             style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {[7, 30, 90, 365].map(d => (
            <button key={d}
                    role="tab" aria-selected={days === d}
                    onClick={() => setDays(d)}
                    style={{
                      background: days === d ? '#6366F1' : 'transparent',
                      color: days === d ? 'white' : ADMIN_COLORS.text,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      padding: '8px 14px', borderRadius: 6,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      minHeight: 36,
                    }}>{d}d</button>
          ))}
        </div>

        {query.isLoading ? (
          <DashboardSkeleton />
        ) : query.isError ? (
          <ErrorState
            variant={query.error?.variant || 'generic'}
            detail={query.error?.detail}
            onRetry={query.refetch}
            description={
              query.error?.variant === 'forbidden'
              ? 'Esta página está disponível apenas para vendedores ou admins.'
              : undefined
            }
          />
        ) : query.data && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
              <StatCard label="Gross Revenue"
                        value={`${fmtKz(query.data.totals.gross_revenue)} Kz`}
                        sub={`${query.data.totals.order_count} orders`} />
              <StatCard label="Net Revenue"
                        value={`${fmtKz(query.data.totals.net_revenue)} Kz`}
                        sub={`${fmtKz(query.data.totals.refunded)} Kz refunded`} />
              <StatCard label="Avg Order Value"
                        value={`${fmtKz(query.data.totals.avg_order_value)} Kz`} />
              <StatCard label="Repeat Rate"
                        value={`${query.data.repeat_rate.rate_pct}%`}
                        sub={`${query.data.repeat_rate.repeat_buyers}/${query.data.repeat_rate.total_buyers} buyers`} />
            </div>

            <Section title="Revenue (daily)"
                     empty={query.data.totals.order_count === 0
                            ? 'Sem vendas no período. Tenta uma janela maior.'
                            : null}>
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={query.data.revenue}>
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
                    { stage: 'View', n: query.data.funnel.counts.view },
                    { stage: 'Cart', n: query.data.funnel.counts.add_cart },
                    { stage: 'Checkout', n: query.data.funnel.counts.checkout },
                    { stage: 'Purchase', n: query.data.funnel.counts.purchase },
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
              <div style={{ marginTop: 8, fontSize: 12, color: ADMIN_COLORS.muted }}>
                View → purchase: {query.data.funnel.view_to_purchase_pct}%
              </div>
            </Section>

            <Section title="Top Products by Revenue"
                     empty={(query.data.top_products?.by_revenue || []).length === 0
                            ? 'Sem vendas neste período.' : null}>
              {(query.data.top_products?.by_revenue || []).map(p => (
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

            <Section title="Top Cities"
                     empty={query.data.geo.length === 0 ? 'Sem dados geográficos.' : null}>
              {query.data.geo.map(g => (
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
