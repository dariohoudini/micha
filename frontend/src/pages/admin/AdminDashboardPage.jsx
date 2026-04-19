import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'

function StatCard({ label, value, sub, color, path, loading }) {
  const navigate = useNavigate()
  return (
    <button onClick={() => path && navigate(path)}
      style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${ADMIN_COLORS.border}`, padding: 14, textAlign: 'left', cursor: path ? 'pointer' : 'default' }}>
      {loading ? (
        <div style={{ height: 48, display: 'flex', alignItems: 'center' }}>
          <div style={{ width: 60, height: 20, background: ADMIN_COLORS.border, borderRadius: 6, animation: 'pulse 1.5s infinite' }}>
            <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
          </div>
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

export default function AdminDashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [revenue, setRevenue] = useState([])
  const [loading, setLoading] = useState(true)
  const [period, setPeriod] = useState(7)

  useEffect(() => {
    loadStats()
    loadRevenue()
  }, [period])

  const loadStats = async () => {
    try {
      const res = await client.get('/api/admin/stats/')
      setStats(res.data)
    } catch (err) {
      console.error('Admin stats failed:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadRevenue = async () => {
    try {
      const res = await client.get(`/api/admin/revenue/?period=${period}`)
      setRevenue(res.data.data || [])
    } catch {}
  }

  const maxGMV = Math.max(...revenue.map(d => d.gmv), 1)

  const formatKz = (n) => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M Kz`
    if (n >= 1000) return `${(n / 1000).toFixed(0)}K Kz`
    return `${n} Kz`
  }

  const ALERT_ITEMS = [
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
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981' }} />
              <span style={{ fontSize: 12, color: '#10b981', fontWeight: 600 }}>Todos os sistemas operacionais</span>
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: ADMIN_COLORS.text, marginBottom: 2 }}>MICHA Express Control</h2>
            <p style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>
              {stats?.users?.total?.toLocaleString() || '—'} utilizadores · {stats?.users?.sellers?.toLocaleString() || '—'} vendedores
            </p>
          </div>

          {/* Urgent alerts */}
          {ALERT_ITEMS.filter(a => a.urgent).length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <h3 style={{ fontSize: 11, fontWeight: 600, color: ADMIN_COLORS.muted, letterSpacing: '0.1em', textTransform: 'uppercase' }}>⚠️ Atenção imediata</h3>
              {ALERT_ITEMS.filter(a => a.urgent).map(alert => (
                <button key={alert.label} onClick={() => navigate(alert.path)}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, cursor: 'pointer', textAlign: 'left', background: `${alert.color}10`, border: `1px solid ${alert.color}30` }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: alert.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: ADMIN_COLORS.text, flex: 1 }}>{alert.label}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
                </button>
              ))}
            </div>
          )}

          {/* Stats grid */}
          <div>
            <h3 style={{ fontSize: 11, fontWeight: 600, color: ADMIN_COLORS.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>Métricas da plataforma</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <StatCard label="Utilizadores" value={stats?.users?.total?.toLocaleString()} sub={`+${stats?.users?.today || 0} hoje`} color="#6366f1" path="/admin/users" loading={loading} />
              <StatCard label="Vendedores" value={stats?.users?.sellers?.toLocaleString()} sub="activos" color="#f59e0b" path="/admin/sellers" loading={loading} />
              <StatCard label="Pedidos hoje" value={stats?.orders?.today?.toLocaleString()} sub={stats?.orders?.gmv_change_pct !== undefined ? `${stats.orders.gmv_change_pct > 0 ? '+' : ''}${stats.orders.gmv_change_pct}% vs ontem` : ''} color="#10b981" path="/admin/orders" loading={loading} />
              <StatCard label="GMV hoje" value={stats?.orders?.gmv_today !== undefined ? formatKz(stats.orders.gmv_today) : '—'} sub="volume total" color="#ec4899" loading={loading} />
              <StatCard label="Produtos" value={stats?.products?.active?.toLocaleString()} sub={`${stats?.products?.pending_review || 0} para moderar`} color="#8b5cf6" path="/admin/products" loading={loading} />
              <StatCard label="AI activo" value={stats?.ai?.profiles_with_quiz?.toLocaleString()} sub={`${stats?.ai?.searches_today || 0} pesquisas hoje`} color="#06b6d4" loading={loading} />
            </div>
          </div>

          {/* Revenue chart */}
          <div style={{ background: ADMIN_COLORS.card, borderRadius: 16, border: `1px solid ${ADMIN_COLORS.border}`, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <p style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 4 }}>GMV — {period} dias</p>
                <p style={{ fontSize: 22, fontWeight: 700, color: '#818cf8' }}>
                  {formatKz(revenue.reduce((a, d) => a + d.gmv, 0))}
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
            {revenue.length > 0 ? (
              <>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 80, marginBottom: 8 }}>
                  {revenue.map((d, i) => (
                    <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                      <div style={{ width: '100%', borderRadius: '3px 3px 0 0', height: `${(d.gmv / maxGMV) * 100}%`, minHeight: d.gmv > 0 ? 4 : 2, background: i === revenue.length - 1 ? '#6366f1' : 'rgba(99,102,241,0.3)', transition: 'height 0.4s ease' }} />
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  {revenue.map((d, i) => (
                    <span key={i} style={{ flex: 1, fontSize: 8, color: ADMIN_COLORS.muted, textAlign: 'center' }}>{d.day}</span>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <p style={{ fontSize: 13, color: ADMIN_COLORS.muted }}>Sem dados de receita ainda.</p>
              </div>
            )}
          </div>

          {/* Other alerts */}
          {ALERT_ITEMS.length > 0 && (
            <div>
              <h3 style={{ fontSize: 11, fontWeight: 600, color: ADMIN_COLORS.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>Acções pendentes</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {ALERT_ITEMS.filter(a => !a.urgent).map(alert => (
                  <button key={alert.label} onClick={() => navigate(alert.path)}
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, cursor: 'pointer', textAlign: 'left', background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}` }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: alert.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 13, color: ADMIN_COLORS.text, flex: 1 }}>{alert.label}</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
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
