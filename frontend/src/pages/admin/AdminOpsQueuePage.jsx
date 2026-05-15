import { useEffect, useState, useCallback } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'

const G = '#C9A84C'
const CARD = '#111'
const BORDER = '#1E1E1E'
const TEXT = '#fff'
const MUTED = '#9A9A9A'
const RED = '#EF4444'
const AMBER = '#F59E0B'
const GREEN = '#059669'
const BLUE = '#3B82F6'
const S = { fontFamily: "'DM Sans', sans-serif" }

const SEVERITY_COLOR = { critical: '#FF0000', high: RED, medium: AMBER, low: GREEN, info: BLUE }

function relTime(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

function Section({ title, count, color, children }) {
  return (
    <section style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 16, marginBottom: 16 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: TEXT, margin: 0 }}>{title}</h2>
        <span style={{ ...S, fontSize: 11, fontWeight: 700, color, padding: '2px 10px', borderRadius: 20, background: `${color}22` }}>
          {count}
        </span>
      </header>
      {children}
    </section>
  )
}

function Empty({ children }) {
  return <p style={{ ...S, fontSize: 12, color: MUTED, margin: 0, padding: '8px 0' }}>{children}</p>
}

export default function AdminOpsQueuePage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState({}) // { 'kind:id': true }
  const [toast, setToast] = useState(null)

  const load = useCallback(() => {
    client.get('/api/v1/admin-api/ops-queue/')
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30s — operators want fresh state
  useEffect(() => {
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const act = async (kind, id, action) => {
    const k = `${kind}:${id}`
    setActing(p => ({ ...p, [k]: true }))
    try {
      const res = await client.post(`/api/v1/admin-api/ops-queue/${kind}/${id}/action/`, { action })
      showToast(res.data?.detail || 'OK')
      load()
    } catch (err) {
      showToast(err.response?.data?.detail || err.response?.data?.error || 'Erro', 'error')
    } finally {
      setActing(p => { const n = { ...p }; delete n[k]; return n })
    }
  }

  if (loading) {
    return (
      <AdminLayout title="Fila de operações">
        <div style={{ padding: 40, textAlign: 'center', ...S, color: MUTED }}>A carregar…</div>
      </AdminLayout>
    )
  }
  if (!data) {
    return (
      <AdminLayout title="Fila de operações">
        <div style={{ padding: 20, ...S, color: RED }}>Não consegui carregar a fila. Tenta de novo.</div>
      </AdminLayout>
    )
  }

  const t = data.totals || {}
  const dangerSum = (t.fraud_holds || 0) + (t.dead_events || 0) + (t.ledger_drift || 0)

  return (
    <AdminLayout title="Fila de operações">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999,
          background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px',
          borderRadius: 12, ...S, fontSize: 13 }}>
          {toast.msg}
        </div>
      )}

      <div style={{ padding: '12px 16px 80px', maxWidth: 980, margin: '0 auto' }}>
        {/* Top summary */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {[
            { label: 'Holds risco', n: t.fraud_holds || 0, color: AMBER },
            { label: 'Eventos mortos', n: t.dead_events || 0, color: RED },
            { label: 'Devoluções pendentes', n: t.pending_returns || 0, color: BLUE },
            { label: 'Drift do ledger', n: t.ledger_drift || 0, color: '#FF0000' },
            { label: 'Alertas recentes', n: t.recent_alerts || 0, color: G },
          ].map(s => (
            <div key={s.label} style={{ flex: '1 1 120px', minWidth: 120, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, padding: 10 }}>
              <p style={{ ...S, fontSize: 10, color: MUTED, margin: 0, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</p>
              <p style={{ ...S, fontSize: 22, fontWeight: 700, color: s.color, margin: '4px 0 0' }}>{s.n}</p>
            </div>
          ))}
        </div>

        {dangerSum === 0 && (
          <div style={{ background: 'rgba(5,150,105,0.08)', border: '1px solid rgba(5,150,105,0.3)', borderRadius: 12, padding: 14, marginBottom: 16, ...S, color: GREEN }}>
            ✓ Nada urgente neste momento.
          </div>
        )}

        {/* Ledger drift — most urgent */}
        <Section title="💰 Drift do ledger" count={t.ledger_drift || 0} color={RED}>
          {(data.ledger_drift || []).length === 0
            ? <Empty>Saldo equilibrado em todas as moedas. ✓</Empty>
            : data.ledger_drift.map(d => (
                <div key={d.currency} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 10px', background: 'rgba(255,0,0,0.06)', borderRadius: 10, marginBottom: 6 }}>
                  <span style={{ ...S, fontSize: 13, color: TEXT, fontWeight: 600 }}>{d.currency}</span>
                  <span style={{ ...S, fontSize: 13, color: RED, fontWeight: 700 }}>
                    {d.imbalance_human} ({d.credits} créditos / {d.debits} débitos)
                  </span>
                </div>
              ))}
        </Section>

        {/* Dead outbox events */}
        <Section title="☠️ Eventos mortos (outbox)" count={t.dead_events || 0} color={RED}>
          {(data.dead_events || []).length === 0
            ? <Empty>Sem eventos mortos.</Empty>
            : data.dead_events.map(e => (
                <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 10, background: '#0A0A0A', borderRadius: 10, marginBottom: 6, border: `1px solid ${BORDER}` }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ ...S, fontSize: 12, fontWeight: 600, color: TEXT, margin: 0 }}>
                      {e.topic} <span style={{ color: MUTED, fontWeight: 400 }}>· {e.attempts} tentativas</span>
                    </p>
                    <p style={{ ...S, fontSize: 10, color: RED, margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {e.last_error}
                    </p>
                    <p style={{ ...S, fontSize: 10, color: MUTED, margin: '2px 0 0' }}>
                      {e.ref_type}:{e.ref_id} · {relTime(e.updated_at)} atrás
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button
                      onClick={() => act('dead_event', e.id, 'requeue')}
                      disabled={!!acting[`dead_event:${e.id}`]}
                      style={{ padding: '6px 12px', borderRadius: 8, border: 'none', background: G, ...S, fontSize: 11, fontWeight: 700, color: '#000', cursor: 'pointer' }}>
                      Reenviar
                    </button>
                    <button
                      onClick={() => act('dead_event', e.id, 'discard')}
                      disabled={!!acting[`dead_event:${e.id}`]}
                      style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'transparent', ...S, fontSize: 11, color: MUTED, cursor: 'pointer' }}>
                      Descartar
                    </button>
                  </div>
                </div>
              ))}
        </Section>

        {/* Fraud holds */}
        <Section title="🚨 Holds de fraude" count={t.fraud_holds || 0} color={AMBER}>
          {(data.fraud_holds || []).length === 0
            ? <Empty>Sem holds pendentes.</Empty>
            : data.fraud_holds.map(h => (
                <div key={h.id} style={{ padding: 10, background: '#0A0A0A', borderRadius: 10, marginBottom: 6, border: `1px solid ${BORDER}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <span style={{ ...S, fontSize: 11, fontWeight: 700, color: h.action === 'block' ? RED : AMBER, padding: '2px 8px', borderRadius: 4, background: `${h.action === 'block' ? RED : AMBER}22` }}>
                      score {h.score} · {h.action}
                    </span>
                    <span style={{ ...S, fontSize: 11, color: TEXT, fontWeight: 500 }}>{h.user_email || 'anon'}</span>
                    <span style={{ ...S, fontSize: 10, color: MUTED, marginLeft: 'auto' }}>{relTime(h.created_at)}</span>
                  </div>
                  <ul style={{ margin: 0, padding: '0 0 0 16px', ...S, fontSize: 11, color: MUTED }}>
                    {(h.reasons || []).slice(0, 3).map((r, i) => <li key={i}>{r.reason}</li>)}
                  </ul>
                  <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                    <button
                      onClick={() => act('fraud_hold', h.id, 'approve')}
                      disabled={!!acting[`fraud_hold:${h.id}`]}
                      style={{ padding: '6px 12px', borderRadius: 8, border: 'none', background: GREEN, ...S, fontSize: 11, fontWeight: 700, color: '#fff', cursor: 'pointer' }}>
                      ✓ Aprovar
                    </button>
                    <button
                      onClick={() => act('fraud_hold', h.id, 'reject')}
                      disabled={!!acting[`fraud_hold:${h.id}`]}
                      style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${RED}`, background: 'transparent', ...S, fontSize: 11, color: RED, cursor: 'pointer' }}>
                      ✗ Bloquear
                    </button>
                  </div>
                </div>
              ))}
        </Section>

        {/* Pending returns */}
        <Section title="↩️ Devoluções pendentes" count={t.pending_returns || 0} color={BLUE}>
          {(data.pending_returns || []).length === 0
            ? <Empty>Sem devoluções a aguardar.</Empty>
            : data.pending_returns.map(r => (
                <div key={r.id} style={{ padding: 10, background: '#0A0A0A', borderRadius: 10, marginBottom: 6, border: `1px solid ${BORDER}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ ...S, fontSize: 11, fontWeight: 700, color: G }}>#{r.order_id.slice(0, 8)}</span>
                    <span style={{ ...S, fontSize: 10, color: r.age_hours > 24 ? RED : MUTED }}>
                      {r.age_hours > 24 ? '⚠ ' : ''}{r.age_hours.toFixed(1)}h
                    </span>
                  </div>
                  <p style={{ ...S, fontSize: 12, color: TEXT, margin: 0 }}>{r.reason} · {r.buyer_email}</p>
                  {r.description && <p style={{ ...S, fontSize: 11, color: MUTED, margin: '4px 0 0' }}>{r.description}</p>}
                </div>
              ))}
        </Section>

        {/* Recent alerts */}
        <Section title="🔔 Alertas recentes" count={t.recent_alerts || 0} color={G}>
          {(data.recent_alerts || []).length === 0
            ? <Empty>Sem alertas recentes.</Empty>
            : data.recent_alerts.map(a => (
                <div key={a.id} style={{ padding: 10, background: '#0A0A0A', borderRadius: 10, marginBottom: 6, border: `1px solid ${BORDER}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ ...S, fontSize: 10, fontWeight: 700, color: SEVERITY_COLOR[a.severity] || MUTED, padding: '1px 7px', borderRadius: 4, background: `${SEVERITY_COLOR[a.severity] || MUTED}22`, textTransform: 'uppercase' }}>
                      {a.severity}
                    </span>
                    <span style={{ ...S, fontSize: 11, color: TEXT, fontWeight: 500 }}>{a.metric}</span>
                    <span style={{ ...S, fontSize: 10, color: MUTED, marginLeft: 'auto' }}>{relTime(a.created_at)}</span>
                  </div>
                  <p style={{ ...S, fontSize: 12, color: MUTED, margin: 0 }}>{a.message}</p>
                </div>
              ))}
        </Section>
      </div>
    </AdminLayout>
  )
}
