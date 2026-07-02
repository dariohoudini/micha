import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'
import { asList } from '@/lib/asList'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

const formatKz = (n) => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M Kz`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K Kz`
  return `${n} Kz`
}

const CHART_COLORS = { gmv: '#818cf8', orders: '#34d399', users: '#f472b6' }

function StatCard({ label, value, sub, color, path, loading }) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => path && navigate(path)}
      style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${ADMIN_COLORS.border}`, padding: 14, textAlign: 'left', cursor: path ? 'pointer' : 'default' }}
    >
      {loading ? (
        <div style={{ height: 48, display: 'flex', alignItems: 'center' }}>
          <div className="skeleton" style={{ width: 60, height: 20, borderRadius: 6 }} />
        </div>
      ) : (
        <>
          <p style={{ fontSize: 22, fontWeight: 700, color: color || ADMIN_COLORS.text, marginBottom: 2 }}>{value ?? '—'}</p>
          <p style={{ fontSize: 12, color: ADMIN_COLORS.text, marginBottom: 2 }}>{label}</p>
          {sub && <p style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>{sub}</p>}
        </>
      )}
    </button>
  )
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '8px 12px' }}>
      <p style={{ fontSize: 11, color: '#9A9A9A', marginBottom: 4 }}>{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ fontSize: 13, fontWeight: 600, color: p.color }}>
          {p.name}: {p.dataKey === 'gmv' ? formatKz(p.value) : p.value?.toLocaleString()}
        </p>
      ))}
    </div>
  )
}

export default function AdminDashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [revenue, setRevenue] = useState([])
  const [fraudAlerts, setFraudAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [chartMetric, setChartMetric] = useState('gmv')
  const [period, setPeriod] = useState(7)

  useEffect(() => {
    loadStats()
    loadRevenue()
    loadFraudAlerts()
  }, [period])

  const loadStats = async () => {
    try {
      const res = await client.get('/api/v1/admin-api/stats/')
      setStats(res.data)
    } catch {}
    finally { setLoading(false) }
  }

  const loadRevenue = async () => {
    try {
      const res = await client.get(`/api/v1/admin-api/revenue/?period=${period}`)
      setRevenue(res.data.data || [])
    } catch {}
  }

  const loadFraudAlerts = async () => {
    try {
      const res = await client.get('/api/v1/security/fraud-alerts/?limit=5')
      setFraudAlerts(asList(res.data))
    } catch {}
  }

  const totalGMV = revenue.reduce((a, d) => a + (d.gmv || 0), 0)
  const totalOrders = revenue.reduce((a, d) => a + (d.orders || 0), 0)

  const ALERTS = [
    { label: `${stats?.orders?.disputes || 0} disputas abertas`, color: '#ef4444', path: '/admin/orders', urgent: (stats?.orders?.disputes || 0) > 0 },
    { label: `${stats?.orders?.pending || 0} pedidos pendentes`, color: '#f59e0b', path: '/admin/orders', urgent: false },
    { label: `${stats?.products?.pending_review || 0} produtos para moderar`, color: '#8b5cf6', path: '/admin/products', urgent: false },
  ].filter(a => parseInt(a.label) > 0)

  return (
    <AdminLayout title="Dashboard">
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Platform health */}
          <div style={{ background: `linear-gradient(135deg, ${ADMIN_COLORS.surface}, ${ADMIN_COLORS.card})`, borderRadius: 16, border: `1px solid ${ADMIN_COLORS.border}`, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 8px #10b981' }} />
              <span style={{ fontSize: 12, color: '#10b981', fontWeight: 600 }}>Todos os sistemas operacionais</span>
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: ADMIN_COLORS.text, marginBottom: 2 }}>MICHA Express Control</h2>
            <p style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>
              {stats?.users?.total?.toLocaleString() || '—'} utilizadores · {stats?.users?.sellers?.toLocaleString() || '—'} vendedores
            </p>
          </div>

          {/* Urgent alerts */}
          {ALERTS.filter(a => a.urgent).length > 0 && (
            <div>
              <h3 style={{ fontSize: 11, fontWeight: 600, color: '#ef4444', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>⚠️ Atenção imediata</h3>
              {ALERTS.filter(a => a.urgent).map(alert => (
                <button key={alert.label} onClick={() => navigate(alert.path)}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, cursor: 'pointer', textAlign: 'left', background: `${alert.color}10`, border: `1px solid ${alert.color}30`, width: '100%', marginBottom: 6 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: alert.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: ADMIN_COLORS.text, flex: 1 }}>{alert.label}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round"><path d="M9 18l6-6-6-6" /></svg>
                </button>
              ))}
            </div>
          )}

          {/* Stats grid */}
          <div>
            <h3 style={{ fontSize: 11, fontWeight: 600, color: ADMIN_COLORS.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>Métricas da plataforma</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <StatCard label="Utilizadores" value={stats?.users?.total?.toLocaleString()} sub={`+${stats?.users?.today || 0} hoje`} color="#818cf8" path="/admin/users" loading={loading} />
              <StatCard label="Vendedores" value={stats?.users?.sellers?.toLocaleString()} sub="activos" color="#f59e0b" path="/admin/sellers" loading={loading} />
              <StatCard label="Pedidos hoje" value={stats?.orders?.today?.toLocaleString()} sub={stats?.orders?.gmv_change_pct !== undefined ? `${stats.orders.gmv_change_pct > 0 ? '+' : ''}${stats.orders.gmv_change_pct}% vs ontem` : ''} color="#34d399" path="/admin/orders" loading={loading} />
              <StatCard label="GMV hoje" value={stats?.orders?.gmv_today !== undefined ? formatKz(stats.orders.gmv_today) : '—'} sub="volume total" color="#f472b6" loading={loading} />
              <StatCard label="Produtos activos" value={stats?.products?.active?.toLocaleString()} sub={`${stats?.products?.pending_review || 0} para moderar`} color="#a78bfa" path="/admin/products" loading={loading} />
              <StatCard label="AI activo" value={stats?.ai?.profiles_with_quiz?.toLocaleString()} sub={`${stats?.ai?.searches_today || 0} pesquisas hoje`} color="#22d3ee" loading={loading} />
            </div>
          </div>

          {/* Revenue chart */}
          <div style={{ background: ADMIN_COLORS.card, borderRadius: 16, border: `1px solid ${ADMIN_COLORS.border}`, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
              <div>
                <p style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 2 }}>
                  {chartMetric === 'gmv' ? 'GMV Total' : chartMetric === 'orders' ? 'Pedidos' : 'Novos utilizadores'} — {period} dias
                </p>
                <p style={{ fontSize: 22, fontWeight: 700, color: CHART_COLORS[chartMetric] }}>
                  {chartMetric === 'gmv' ? formatKz(totalGMV) : totalOrders.toLocaleString()}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {[7, 14, 30].map(p => (
                  <button key={p} onClick={() => setPeriod(p)}
                    style={{ padding: '4px 10px', borderRadius: 8, border: `1px solid ${period === p ? '#6366f1' : ADMIN_COLORS.border}`, background: period === p ? 'rgba(99,102,241,0.1)' : 'transparent', fontSize: 11, color: period === p ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer' }}>
                    {p}d
                  </button>
                ))}
              </div>
            </div>

            {/* Metric tabs */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
              {[
                { k: 'gmv', l: 'Receita' },
                { k: 'orders', l: 'Pedidos' },
                { k: 'users', l: 'Utilizadores' },
              ].map(t => (
                <button key={t.k} onClick={() => setChartMetric(t.k)}
                  style={{ padding: '4px 12px', borderRadius: 20, border: `1px solid ${chartMetric === t.k ? CHART_COLORS[t.k] : ADMIN_COLORS.border}`, background: chartMetric === t.k ? `${CHART_COLORS[t.k]}15` : 'transparent', fontSize: 11, color: chartMetric === t.k ? CHART_COLORS[t.k] : ADMIN_COLORS.muted, cursor: 'pointer', fontWeight: chartMetric === t.k ? 600 : 400 }}>
                  {t.l}
                </button>
              ))}
            </div>

            {revenue.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={revenue} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="adminGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={CHART_COLORS[chartMetric]} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={CHART_COLORS[chartMetric]} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E1E1E" vertical={false} />
                  <XAxis dataKey="day" tick={{ fill: '#555', fontSize: 9 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#555', fontSize: 9 }} axisLine={false} tickLine={false}
                    tickFormatter={v => chartMetric === 'gmv' ? formatKz(v) : v.toLocaleString()} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey={chartMetric} stroke={CHART_COLORS[chartMetric]} strokeWidth={2}
                    fill="url(#adminGrad)" dot={false} activeDot={{ r: 4, fill: CHART_COLORS[chartMetric] }}
                    name={chartMetric === 'gmv' ? 'Receita' : chartMetric === 'orders' ? 'Pedidos' : 'Utilizadores'} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <p style={{ fontSize: 13, color: ADMIN_COLORS.muted }}>Sem dados de receita ainda.</p>
              </div>
            )}
          </div>

          {/* Fraud alerts from AI engine */}
          {fraudAlerts.length > 0 && (
            <div>
              <h3 style={{ fontSize: 11, fontWeight: 600, color: '#ef4444', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>🛡️ Alertas de fraude</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {fraudAlerts.map((alert, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(239,68,68,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: 13, color: ADMIN_COLORS.text, fontWeight: 500, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {alert.reason || alert.message || 'Actividade suspeita detectada'}
                      </p>
                      <p style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>
                        Score: {(alert.risk_score * 100).toFixed(0)}% · {alert.user_email || alert.user || '—'}
                      </p>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: alert.risk_score > 0.8 ? '#ef4444' : '#f59e0b', background: alert.risk_score > 0.8 ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)', padding: '3px 8px', borderRadius: 6, flexShrink: 0 }}>
                      {alert.risk_score > 0.8 ? 'ALTO' : 'MÉDIO'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pending actions */}
          {ALERTS.filter(a => !a.urgent).length > 0 && (
            <div>
              <h3 style={{ fontSize: 11, fontWeight: 600, color: ADMIN_COLORS.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>Acções pendentes</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {ALERTS.filter(a => !a.urgent).map(alert => (
                  <button key={alert.label} onClick={() => navigate(alert.path)}
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, cursor: 'pointer', textAlign: 'left', background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`, width: '100%' }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: alert.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 13, color: ADMIN_COLORS.text, flex: 1 }}>{alert.label}</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round"><path d="M9 18l6-6-6-6" /></svg>
                  </button>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </AdminLayout>
  )
}
