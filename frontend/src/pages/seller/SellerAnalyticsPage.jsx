import { useState, useEffect } from 'react'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const fmtK = (n) => n >= 1000 ? `${(n / 1000).toFixed(0)}K` : String(n)
const S = { fontFamily: "'DM Sans', sans-serif" }

const GOLD = '#C9A84C'
const GOLD2 = 'rgba(201,168,76,0.15)'
const BLUE = '#3b82f6'
const GREEN = '#10b981'
const PURPLE = '#8b5cf6'
const PIE_COLORS = [GOLD, BLUE, GREEN, PURPLE, '#f59e0b', '#ef4444']

function StatCard({ label, value, sub, color = '#FFF', loading }) {
  return (
    <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
      {loading
        ? <><div className="skeleton" style={{ height: 22, width: '60%', borderRadius: 6, marginBottom: 6 }} /><div className="skeleton" style={{ height: 11, width: '40%', borderRadius: 5 }} /></>
        : <>
            <p style={{ ...S, fontSize: 20, fontWeight: 700, color, marginBottom: 2 }}>{value}</p>
            <p style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>{label}</p>
            {sub && <p style={{ ...S, fontSize: 10, color: '#059669', marginTop: 3 }}>{sub}</p>}
          </>
      }
    </div>
  )
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '8px 12px' }}>
      <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 4 }}>{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ ...S, fontSize: 13, fontWeight: 600, color: p.color }}>{p.name === 'revenue' ? fmt(p.value) : p.value}</p>
      ))}
    </div>
  )
}

export default function SellerAnalyticsPage() {
  const [data, setData] = useState(null)
  const [period, setPeriod] = useState(7)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('revenue')

  useEffect(() => {
    setLoading(true)
    client.get(`/api/v1/analytics/seller/performance/?period=${period}&include_chart=true`)
      .then(res => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [period])

  const chartData = (data?.chart || []).map(d => ({
    day: d.day || d.date || '',
    revenue: Number(d.revenue || 0),
    orders: Number(d.orders || 0),
    views: Number(d.views || 0),
  }))

  const topProducts = data?.top_products || []
  const categoryBreakdown = data?.category_breakdown || []
  const conversionRate = data?.conversion_rate ? `${(data.conversion_rate * 100).toFixed(1)}%` : '—'

  return (
    <SellerLayout title="Análises">
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Period selector */}
          <div style={{ display: 'flex', gap: 8 }}>
            {[7, 14, 30, 90].map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: `1px solid ${period === p ? GOLD : '#2A2A2A'}`, background: period === p ? GOLD2 : 'transparent', ...S, fontSize: 12, color: period === p ? GOLD : '#9A9A9A', cursor: 'pointer', fontWeight: period === p ? 600 : 400 }}>
                {p}d
              </button>
            ))}
          </div>

          {/* KPI cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <StatCard label="Receita total" value={fmt(data?.total_revenue)} color={GOLD} loading={loading}
              sub={data?.revenue_growth ? `+${data.revenue_growth}% vs período anterior` : null} />
            <StatCard label="Pedidos" value={data?.total_orders ?? '—'} loading={loading}
              sub={data?.orders_growth ? `+${data.orders_growth}% crescimento` : null} />
            <StatCard label="Visitas" value={data?.total_views ?? '—'} loading={loading} />
            <StatCard label="Conversão" value={conversionRate} color={GREEN} loading={loading} />
            <StatCard label="Avaliação média" value={data?.avg_rating ? `★ ${Number(data.avg_rating).toFixed(1)}` : '—'} color={GOLD} loading={loading} />
            <StatCard label="Ticket médio" value={data?.avg_order_value ? fmt(data.avg_order_value) : '—'} loading={loading} />
          </div>

          {/* Chart tabs */}
          {!loading && chartData.length > 0 && (
            <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
              <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
                {[
                  { key: 'revenue', label: 'Receita', color: GOLD },
                  { key: 'orders',  label: 'Pedidos', color: BLUE },
                  { key: 'views',   label: 'Visitas', color: PURPLE },
                ].map(t => (
                  <button key={t.key} onClick={() => setActiveTab(t.key)}
                    style={{ padding: '5px 12px', borderRadius: 8, border: `1px solid ${activeTab === t.key ? t.color : '#2A2A2A'}`, background: activeTab === t.key ? `${t.color}18` : 'transparent', ...S, fontSize: 11, color: activeTab === t.key ? t.color : '#9A9A9A', cursor: 'pointer', fontWeight: activeTab === t.key ? 600 : 400 }}>
                    {t.label}
                  </button>
                ))}
              </div>

              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <defs>
                    <linearGradient id="colorGold" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={GOLD} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={GOLD} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorBlue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={BLUE} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={BLUE} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorPurple" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={PURPLE} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={PURPLE} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E1E1E" vertical={false} />
                  <XAxis dataKey="day" tick={{ ...S, fontSize: 9, fill: '#9A9A9A' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ ...S, fontSize: 9, fill: '#9A9A9A' }} axisLine={false} tickLine={false}
                    tickFormatter={activeTab === 'revenue' ? fmtK : undefined} />
                  <Tooltip content={<CustomTooltip />} />
                  {activeTab === 'revenue' && <Area type="monotone" dataKey="revenue" name="revenue" stroke={GOLD} strokeWidth={2} fill="url(#colorGold)" dot={false} activeDot={{ r: 4, fill: GOLD }} />}
                  {activeTab === 'orders'  && <Area type="monotone" dataKey="orders"  name="orders"  stroke={BLUE}   strokeWidth={2} fill="url(#colorBlue)"   dot={false} activeDot={{ r: 4, fill: BLUE }} />}
                  {activeTab === 'views'   && <Area type="monotone" dataKey="views"   name="views"   stroke={PURPLE} strokeWidth={2} fill="url(#colorPurple)" dot={false} activeDot={{ r: 4, fill: PURPLE }} />}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top products bar chart */}
          {!loading && topProducts.length > 0 && (
            <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
              <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#FFF', marginBottom: 16 }}>Top produtos por receita</p>
              <ResponsiveContainer width="100%" height={Math.min(topProducts.length * 44 + 20, 220)}>
                <BarChart data={topProducts} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E1E1E" horizontal={false} />
                  <XAxis type="number" tick={{ ...S, fontSize: 9, fill: '#9A9A9A' }} axisLine={false} tickLine={false} tickFormatter={fmtK} />
                  <YAxis type="category" dataKey="name" tick={{ ...S, fontSize: 10, fill: '#CCCCCC' }} axisLine={false} tickLine={false} width={90} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="revenue" name="revenue" fill={GOLD} radius={[0, 6, 6, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Category breakdown donut */}
          {!loading && categoryBreakdown.length > 0 && (
            <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
              <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#FFF', marginBottom: 16 }}>Vendas por categoria</p>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={categoryBreakdown} dataKey="value" nameKey="name" cx="50%" cy="50%"
                    innerRadius={45} outerRadius={72} paddingAngle={3} strokeWidth={0}>
                    {categoryBreakdown.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Legend iconType="circle" iconSize={8}
                    formatter={(v) => <span style={{ ...S, fontSize: 11, color: '#CCCCCC' }}>{v}</span>} />
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Loading skeletons */}
          {loading && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 72, borderRadius: 14 }} />)}
              </div>
              <div className="skeleton" style={{ height: 200, borderRadius: 16 }} />
              <div className="skeleton" style={{ height: 180, borderRadius: 16 }} />
            </>
          )}

          {!loading && !data && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 0', gap: 12 }}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg>
              <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>Sem dados para este período.</p>
            </div>
          )}
        </div>
      </div>
    </SellerLayout>
  )
}
