import { useState, useEffect, useRef } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E'
const TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444', BLUE = '#3B82F6', ORANGE = '#F59E0B'

const STATUS_COLOR = { success: GREEN, failure: RED, retry: ORANGE, started: BLUE }
const STATUS_LABEL = { success: '✅ OK', failure: '❌ FAILED', retry: '⚠️ RETRY', started: '⏳ Running' }

function StatCard({ label, value, color = TEXT, sub }) {
  return (
    <div style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: '14px 16px' }}>
      <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</p>
      <p style={{ fontFamily: "'Playfair Display'", fontSize: 26, fontWeight: 700, color, margin: 0 }}>{value}</p>
      {sub && <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: '4px 0 0' }}>{sub}</p>}
    </div>
  )
}

export default function AdminMonitoringPage() {
  const [data, setData] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('overview')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const intervalRef = useRef(null)

  const load = async () => {
    try {
      const [monRes, healthRes] = await Promise.allSettled([
        client.get('/api/v1/monitoring/tasks/'),
        client.get('/api/v1/monitoring/tasks/health/'),
      ])
      if (monRes.status === 'fulfilled') setData(monRes.value.data)
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data)
    } catch {}
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 15000)
    } else {
      clearInterval(intervalRef.current)
    }
    return () => clearInterval(intervalRef.current)
  }, [autoRefresh])

  const s = data?.stats || {}
  const failRate = s.total ? ((s.failed / s.total) * 100).toFixed(1) : '0.0'
  const successRate = s.total ? ((s.success / s.total) * 100).toFixed(1) : '0.0'

  return (
    <AdminLayout title="Monitorização">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 22, fontWeight: 700, color: TEXT, margin: '0 0 4px' }}>Monitorização de Tarefas</h1>
            <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: 0 }}>
              {health?.healthy === true ? '✅ Sistema saudável' : health?.healthy === false ? `❌ ${health.issues?.length} problema(s)` : '⏳ A verificar...'}
              {' · '}{data?.scheduled_count || 28} tarefas agendadas
            </p>
          </div>
          <button onClick={() => setAutoRefresh(!autoRefresh)} style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${autoRefresh ? GREEN : BORDER}`, background: autoRefresh ? 'rgba(5,150,105,0.1)' : 'none', color: autoRefresh ? GREEN : MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
            {autoRefresh ? '⟳ Auto' : '⟳ Manual'}
          </button>
        </div>

        {/* Health alerts */}
        {health?.issues?.length > 0 && (
          <div style={{ background: 'rgba(239,68,68,0.08)', border: `1px solid rgba(239,68,68,0.3)`, borderRadius: 12, padding: 14, marginBottom: 16 }}>
            <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: RED, margin: '0 0 8px' }}>⚠️ Alertas críticos</p>
            {health.issues.map((issue, i) => (
              <p key={i} style={{ fontFamily: "'DM Sans'", fontSize: 12, color: RED, margin: '0 0 4px' }}>• {issue.task}: {issue.issue}</p>
            ))}
          </div>
        )}

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
          <StatCard label="Execuções (24h)" value={s.total || 0} color={G} />
          <StatCard label="Taxa de sucesso" value={`${successRate}%`} color={Number(successRate) > 95 ? GREEN : Number(successRate) > 80 ? ORANGE : RED} />
          <StatCard label="Falhas" value={s.failed || 0} color={s.failed > 0 ? RED : GREEN} sub={`${failRate}% de falha`} />
          <StatCard label="Duração média" value={s.avg_duration ? `${Number(s.avg_duration).toFixed(1)}s` : 'N/A'} color={BLUE} />
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {['overview', 'failures', 'all_tasks'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ padding: '7px 12px', borderRadius: 8, border: `1.5px solid ${tab === t ? G : BORDER}`, background: tab === t ? 'rgba(201,168,76,0.1)' : 'none', color: tab === t ? G : MUTED, fontFamily: "'DM Sans'", fontSize: 11, fontWeight: tab === t ? 600 : 400, cursor: 'pointer' }}>
              {t === 'overview' ? 'Visão geral' : t === 'failures' ? `Falhas (${s.failed || 0})` : 'Todas as tarefas'}
            </button>
          ))}
        </div>

        {/* Overview - last run per task */}
        {tab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED, fontSize: 13 }}>A carregar...</p> :
              Object.entries(data?.last_runs || {}).map(([name, info]) => (
                <div key={name} style={{ background: CARD, borderRadius: 10, border: `1px solid ${info.status === 'failure' ? 'rgba(239,68,68,0.3)' : BORDER}`, padding: '11px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 500, color: TEXT, margin: '0 0 2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {name.split('.').pop()}
                    </p>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 10, color: MUTED, margin: 0 }}>
                      {new Date(info.started_at).toLocaleString('pt-AO')} · {info.duration}
                    </p>
                  </div>
                  <span style={{ padding: '2px 8px', borderRadius: 4, background: `${STATUS_COLOR[info.status] || MUTED}20`, color: STATUS_COLOR[info.status] || MUTED, fontFamily: "'DM Sans'", fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
                    {STATUS_LABEL[info.status] || info.status}
                  </span>
                </div>
              ))
            }
            {!loading && Object.keys(data?.last_runs || {}).length === 0 && (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <p style={{ fontFamily: "'DM Sans'", fontSize: 14, color: MUTED }}>Sem dados ainda — inicia o Celery beat para ver execuções</p>
                <code style={{ fontFamily: 'monospace', fontSize: 11, color: G, background: CARD, padding: '8px 12px', borderRadius: 8, display: 'inline-block', marginTop: 8 }}>
                  celery -A config beat --loglevel=info
                </code>
              </div>
            )}
          </div>
        )}

        {/* Failures */}
        {tab === 'failures' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED }}>A carregar...</p> :
              (data?.failing_tasks || []).length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 15, color: GREEN }}>✅ Sem falhas nas últimas 24h</p>
                </div>
              ) : (data?.failing_tasks || []).map((task, i) => (
                <div key={i} style={{ background: CARD, borderRadius: 12, border: '1px solid rgba(239,68,68,0.3)', padding: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: RED, margin: 0 }}>{task.task_name?.split('.').pop()}</p>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: 0 }}>{new Date(task.started_at).toLocaleString('pt-AO')}</p>
                  </div>
                  <p style={{ fontFamily: 'monospace', fontSize: 11, color: MUTED, margin: 0, background: BG, padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all' }}>{task.error_message}</p>
                </div>
              ))
            }
          </div>
        )}

        {/* All tasks stats */}
        {tab === 'all_tasks' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED }}>A carregar...</p> :
              (data?.per_task || []).map((task, i) => {
                const rate = task.runs ? ((task.successes / task.runs) * 100).toFixed(0) : 0
                return (
                  <div key={i} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, padding: '12px 14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 500, color: TEXT, margin: 0 }}>{task.task_name?.split('.').pop()}</p>
                      <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: Number(rate) > 95 ? GREEN : ORANGE }}>{rate}% OK</span>
                    </div>
                    <div style={{ display: 'flex', gap: 12 }}>
                      {[
                        { label: 'Execuções', value: task.runs },
                        { label: 'Sucessos', value: task.successes, color: GREEN },
                        { label: 'Falhas', value: task.failures, color: task.failures > 0 ? RED : MUTED },
                        { label: 'Avg', value: task.avg_duration ? `${Number(task.avg_duration).toFixed(1)}s` : 'N/A' },
                      ].map((m, j) => (
                        <div key={j}>
                          <p style={{ fontFamily: "'DM Sans'", fontSize: 10, color: MUTED, margin: '0 0 1px' }}>{m.label}</p>
                          <p style={{ fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, color: m.color || TEXT, margin: 0 }}>{m.value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })
            }
          </div>
        )}

        {/* Flower link */}
        <div style={{ marginTop: 20, background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: 16 }}>
          <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: TEXT, margin: '0 0 8px' }}>Flower — Monitor Celery avançado</p>
          <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: '0 0 10px' }}>Para ver workers em tempo real, filas, histórico completo e estatísticas detalhadas:</p>
          <code style={{ fontFamily: 'monospace', fontSize: 11, color: G, background: BG, padding: '8px 12px', borderRadius: 8, display: 'block', marginBottom: 8 }}>
            celery -A config flower --port=5555
          </code>
          <a href="http://localhost:5555" target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: `1px solid ${G}`, color: G, fontFamily: "'DM Sans'", fontSize: 12, textDecoration: 'none' }}>
            🌸 Abrir Flower Dashboard
          </a>
        </div>
      </div>
    </AdminLayout>
  )
}
