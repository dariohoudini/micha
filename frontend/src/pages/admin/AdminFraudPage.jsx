import { useState, useEffect, useRef } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E'
const TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444', ORANGE = '#F59E0B', BLUE = '#3B82F6'

const SEVERITY_COLOR = { low: GREEN, medium: ORANGE, high: RED, critical: '#FF0000' }
const ACTION_COLOR = { allow: GREEN, flag: ORANGE, hold: ORANGE, block: RED }
const ACTION_LABEL = { allow: '✅ Permitido', flag: '⚠️ Sinalizado', hold: '🔒 Retido', block: '🚫 Bloqueado' }

function RiskBar({ score }) {
  const color = score >= 80 ? RED : score >= 60 ? ORANGE : score >= 30 ? G : GREEN
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: BORDER, borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${score}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 700, color, minWidth: 28 }}>{score}</span>
    </div>
  )
}

export default function AdminFraudPage() {
  const [alerts, setAlerts] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)
  const intervalRef = useRef(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const load = async () => {
    try {
      const res = await client.get('/api/v1/security/fraud-alerts/')
      const data = res.data.results || res.data || []
      setAlerts(data)

      // Compute stats
      const total = data.length
      const critical = data.filter(a => a.severity === 'critical').length
      const high = data.filter(a => a.severity === 'high').length
      const unresolved = data.filter(a => !a.is_resolved).length
      setStats({ total, critical, high, unresolved })
    } catch {}
    setLoading(false)
  }

  useEffect(() => {
    load()
    intervalRef.current = setInterval(load, 30000)
    return () => clearInterval(intervalRef.current)
  }, [])

  const resolve = async (alertId) => {
    try {
      await client.patch(`/api/v1/security/fraud-alerts/${alertId}/resolve/`, { resolved: true })
      setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, is_resolved: true } : a))
      setSelected(null)
      showToast('Alerta resolvido')
    } catch { showToast('Erro ao resolver', 'error') }
  }

  const filtered = alerts.filter(a => {
    if (filter === 'unresolved') return !a.is_resolved
    if (filter === 'critical') return a.severity === 'critical'
    if (filter === 'high') return a.severity === 'high'
    return true
  })

  return (
    <AdminLayout title="Fraude">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        {toast && (
          <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, fontFamily: "'DM Sans'", fontSize: 13 }}>
            {toast.msg}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 22, fontWeight: 700, color: TEXT, margin: '0 0 4px' }}>Centro de Fraude</h1>
            <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: 0 }}>
              Actualiza automaticamente a cada 30s
            </p>
          </div>
          {stats?.critical > 0 && (
            <div style={{ padding: '6px 12px', borderRadius: 8, background: 'rgba(255,0,0,0.15)', border: '1px solid rgba(255,0,0,0.4)' }}>
              <span style={{ fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 700, color: RED }}>
                🚨 {stats.critical} CRÍTICO{stats.critical > 1 ? 'S' : ''}
              </span>
            </div>
          )}
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 16 }}>
          {[
            { label: 'Total alertas', value: stats?.total || 0, color: TEXT },
            { label: 'Por resolver', value: stats?.unresolved || 0, color: stats?.unresolved > 0 ? ORANGE : GREEN },
            { label: 'Alta severidade', value: stats?.high || 0, color: stats?.high > 0 ? RED : GREEN },
            { label: 'Críticos', value: stats?.critical || 0, color: stats?.critical > 0 ? '#FF0000' : GREEN },
          ].map((s, i) => (
            <div key={i} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, padding: '10px 12px', textAlign: 'center' }}>
              <p style={{ fontFamily: "'Playfair Display'", fontSize: 20, fontWeight: 700, color: s.color, margin: '0 0 2px' }}>{s.value}</p>
              <p style={{ fontFamily: "'DM Sans'", fontSize: 10, color: MUTED, margin: 0 }}>{s.label}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {['all', 'unresolved', 'critical', 'high'].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ padding: '6px 12px', borderRadius: 8, border: `1.5px solid ${filter === f ? G : BORDER}`, background: filter === f ? 'rgba(201,168,76,0.1)' : 'none', color: filter === f ? G : MUTED, fontFamily: "'DM Sans'", fontSize: 11, fontWeight: filter === f ? 600 : 400, cursor: 'pointer' }}>
              {f === 'all' ? 'Todos' : f === 'unresolved' ? 'Por resolver' : f === 'critical' ? '🚨 Críticos' : '⚠️ Alta'}
            </button>
          ))}
        </div>

        {/* Alert list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading ? (
            <p style={{ fontFamily: "'DM Sans'", color: MUTED, fontSize: 13 }}>A carregar...</p>
          ) : filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <p style={{ fontFamily: "'DM Sans'", fontSize: 15, color: GREEN }}>✅ Sem alertas{filter !== 'all' ? ' nesta categoria' : ''}</p>
            </div>
          ) : filtered.map(alert => (
            <div key={alert.id} style={{
              background: CARD,
              borderRadius: 14,
              border: `1.5px solid ${alert.is_resolved ? BORDER : SEVERITY_COLOR[alert.severity] + '40'}`,
              padding: 14,
              opacity: alert.is_resolved ? 0.6 : 1,
            }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, background: `${SEVERITY_COLOR[alert.severity]}20`, color: SEVERITY_COLOR[alert.severity], fontFamily: "'DM Sans'", fontSize: 10, fontWeight: 700, textTransform: 'uppercase' }}>
                      {alert.severity}
                    </span>
                    <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED }}>
                      {new Date(alert.created_at).toLocaleString('pt-AO')}
                    </span>
                    {alert.is_resolved && (
                      <span style={{ padding: '2px 8px', borderRadius: 4, background: 'rgba(5,150,105,0.15)', color: GREEN, fontFamily: "'DM Sans'", fontSize: 10 }}>✓ Resolvido</span>
                    )}
                  </div>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: TEXT, margin: 0 }}>
                    {alert.type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </p>
                </div>
                {!alert.is_resolved && (
                  <button onClick={() => setSelected(selected === alert.id ? null : alert.id)} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                    Acções
                  </button>
                )}
              </div>

              {/* Description */}
              <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: '0 0 10px', lineHeight: 1.5 }}>
                {alert.description}
              </p>

              {/* Risk score bar */}
              {alert.risk_score !== undefined && (
                <div style={{ marginBottom: 10 }}>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 10, color: MUTED, margin: '0 0 4px' }}>RISCO</p>
                  <RiskBar score={alert.risk_score || 0} />
                </div>
              )}

              {/* Signals breakdown */}
              {alert.signals && alert.signals.length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                  {alert.signals.map((sig, i) => (
                    <span key={i} style={{ padding: '2px 8px', borderRadius: 4, background: `${SEVERITY_COLOR[sig.severity] || MUTED}15`, color: SEVERITY_COLOR[sig.severity] || MUTED, fontFamily: "'DM Sans'", fontSize: 10 }}>
                      {sig.name} (+{sig.score})
                    </span>
                  ))}
                </div>
              )}

              {/* Actions */}
              {selected === alert.id && (
                <div style={{ display: 'flex', gap: 8, paddingTop: 10, borderTop: `1px solid ${BORDER}` }}>
                  <button onClick={() => resolve(alert.id)} style={{ flex: 1, padding: '9px', borderRadius: 10, border: 'none', background: GREEN, color: '#fff', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    ✅ Marcar como resolvido
                  </button>
                  {alert.user_id && (
                    <button onClick={() => window.open(`/admin/users?id=${alert.user_id}`, '_blank')} style={{ padding: '9px 14px', borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans'", fontSize: 12, cursor: 'pointer' }}>
                      Ver utilizador
                    </button>
                  )}
                  {alert.order_id && (
                    <button onClick={() => window.open(`/admin/orders?id=${alert.order_id}`, '_blank')} style={{ padding: '9px 14px', borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans'", fontSize: 12, cursor: 'pointer' }}>
                      Ver pedido
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Signal reference */}
        <div style={{ marginTop: 24, background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 16 }}>
          <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: TEXT, margin: '0 0 12px' }}>Sinais de fraude activos (15)</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { name: 'new_account_high_value', score: 35, desc: 'Conta nova + pedido alto' },
              { name: 'previously_blocked', score: 50, desc: 'Utilizador bloqueado anteriormente' },
              { name: 'extreme_velocity', score: 40, desc: '5+ pedidos em 1 hora' },
              { name: 'serial_dispute_abuser', score: 35, desc: 'Disputas em série perdidas' },
              { name: 'payment_testing_pattern', score: 30, desc: 'Padrão de teste de pagamento' },
              { name: 'shared_ip_fraud_history', score: 30, desc: 'IP com histórico fraudulento' },
              { name: 'device_shared_accounts', score: 30, desc: 'Dispositivo em múltiplas contas' },
              { name: 'ordered_without_viewing', score: 20, desc: 'Pedido sem ver o produto' },
              { name: 'ip_multiple_accounts', score: 25, desc: 'IP com muitas contas' },
              { name: 'multiple_failed_payments', score: 25, desc: 'Pagamentos falhados recentes' },
              { name: 'high_cancellation_rate', score: 20, desc: '>50% pedidos cancelados' },
              { name: 'location_change_before_high_value', score: 20, desc: 'IP mudou antes de pedido alto' },
              { name: 'referral_chain_abuse', score: 20, desc: 'Abuso de referências' },
              { name: 'bulk_single_item', score: 15, desc: 'Compra em massa de 1 produto' },
              { name: 'loyalty_point_manipulation', score: 20, desc: 'Manipulação de pontos' },
            ].map((sig, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', borderRadius: 6, background: BG }}>
                <span style={{ fontFamily: "'DM Sans'", fontSize: 10, color: MUTED }}>{sig.desc}</span>
                <span style={{ fontFamily: "'DM Sans'", fontSize: 10, fontWeight: 700, color: sig.score >= 30 ? RED : ORANGE }}>+{sig.score}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
