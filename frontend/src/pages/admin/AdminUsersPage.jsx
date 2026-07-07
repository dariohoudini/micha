import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'
import { asList } from '@/lib/asList'
import { useAuthStore } from '@/stores/authStore'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444'
const STATUS_COLORS = { active: GREEN, warned: G, suspended: RED, banned: RED }

const LADDER_LABELS = ['L0 · Não verificado', 'L1 · Contacto verificado', 'L2 · 2FA activo', 'L3 · KYC aprovado']
const RISK_COLORS = { low: GREEN, elevated: '#F59E0B', high: RED }

export default function AdminUsersPage() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [toast, setToast] = useState(null)
  const [selected, setSelected] = useState(null)
  const [inspecting, setInspecting] = useState(null)   // user object
  const [inspector, setInspector] = useState(null)     // panel payload
  const [inspBusy, setInspBusy] = useState(false)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  const openInspector = async (u) => {
    setInspecting(u); setInspector(null)
    try {
      const r = await client.get(`/api/v1/admin-api/users/${u.id}/inspector/`)
      setInspector(r.data)
    } catch { showToast('Erro ao abrir o inspector', 'error'); setInspecting(null) }
  }

  const terminateSessions = async () => {
    setInspBusy(true)
    try {
      const r = await client.post(`/api/v1/admin-api/users/${inspecting.id}/sessions/terminate/`)
      showToast(`Sessões terminadas (${r.data.sessions_terminated}) · tokens revogados (${r.data.tokens_revoked})`)
      openInspector(inspecting)
    } catch { showToast('Erro ao terminar sessões', 'error') }
    setInspBusy(false)
  }

  const triggerPasswordReset = async () => {
    setInspBusy(true)
    try {
      await client.post(`/api/v1/admin-api/users/${inspecting.id}/password-reset/`)
      showToast('Código de reset enviado para o email do utilizador')
    } catch { showToast('Erro ao enviar reset', 'error') }
    setInspBusy(false)
  }

  // Graduated restrict (CH5) — toggle one capability. Any active flag
  // means a live restriction; clearing the last one un-restricts.
  const toggleRestriction = async (kind) => {
    const cur = inspector?.access?.restriction || {}
    const next = { selling: !!cur.selling, withdrawal: !!cur.withdrawal, messaging: !!cur.messaging }
    next[kind] = !next[kind]
    const anyOn = next.selling || next.withdrawal || next.messaging
    setInspBusy(true)
    try {
      if (anyOn) {
        const reason = cur.reason || prompt('Motivo da restrição:') || 'Restrição administrativa'
        await client.post(`/api/v1/admin-api/users/${inspecting.id}/action/`, {
          action: 'restrict', reason,
          no_selling: next.selling, no_withdrawal: next.withdrawal, no_messaging: next.messaging,
        })
      } else {
        await client.post(`/api/v1/admin-api/users/${inspecting.id}/action/`, { action: 'unrestrict' })
      }
      showToast('Restrições actualizadas')
      openInspector(inspecting)
    } catch { showToast('Erro ao actualizar restrições', 'error') }
    setInspBusy(false)
  }

  // Impersonation (CH17) — "Ver como". Mint a time-boxed token, hand it
  // to the auth store (which swaps the in-memory session to the target
  // WITHOUT touching the operator's persisted tokens), then drop the
  // operator onto the home feed seeing exactly what the user sees. The
  // fixed banner + safe-exit are handled globally by ImpersonationBanner.
  const impersonate = async () => {
    if (!confirm(`Ver a plataforma como ${inspecting.email}?\n\nAcções sensíveis (pagamentos, password, apagar conta) ficam bloqueadas. A sessão expira em 15 min. Tudo fica registado em auditoria.`)) return
    setInspBusy(true)
    try {
      const r = await client.post(`/api/v1/admin-api/users/${inspecting.id}/impersonate/`)
      await useAuthStore.getState().enterImpersonation(r.data.access, r.data.acting_as)
      if (!useAuthStore.getState().impersonating) { showToast('Não foi possível iniciar a sessão', 'error'); setInspBusy(false); return }
      navigate('/home')
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erro ao iniciar "ver como"', 'error')
      setInspBusy(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    client.get('/api/v1/admin-actions/users/').then(r => setUsers(asList(r.data))).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleAction = async (userId, action, reason = '') => {
    try {
      await client.post(`/api/v1/admin-api/users/${userId}/action/`, { action, reason })
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: action === 'ban' ? 'banned' : action === 'suspend' ? 'suspended' : 'active' } : u))
      setSelected(null)
      showToast(`Utilizador ${action === 'ban' ? 'banido' : action === 'suspend' ? 'suspenso' : 'reactivado'}`)
    } catch { showToast('Erro ao processar', 'error') }
  }

  const filtered = users.filter(u => {
    const matchSearch = !search || u.email?.toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === 'all' || u.status === filter
    return matchSearch && matchFilter
  })

  return (
    <AdminLayout title="Utilizadores">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, fontFamily: "'DM Sans'", fontSize: 13 }}>{toast.msg}</div>}

        <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 16px' }}>Gestão de Utilizadores</h1>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto' }}>
          {['all', 'active', 'warned', 'suspended', 'banned'].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ padding: '7px 12px', borderRadius: 8, border: `1px solid ${filter === f ? G : BORDER}`, background: filter === f ? 'rgba(201,168,76,0.1)' : 'none', color: filter === f ? G : MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}>
              {f === 'all' ? 'Todos' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar por email..." style={{ width: '100%', padding: '11px 14px', background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, color: TEXT, fontFamily: "'DM Sans'", fontSize: 13, outline: 'none', marginBottom: 12, boxSizing: 'border-box' }} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED, fontSize: 13 }}>A carregar...</p> :
            filtered.map(u => (
              <div key={u.id} style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: '13px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: selected === u.id ? 12 : 0 }}>
                  <div>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 500, color: TEXT, margin: '0 0 2px' }}>{u.email}</p>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: 0 }}>
                      Registado: {u.date_joined ? new Date(u.date_joined).toLocaleDateString('pt-AO') : 'N/A'}
                      {u.is_seller ? ' · Vendedor' : ''}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, background: `${STATUS_COLORS[u.status] || MUTED}20`, color: STATUS_COLORS[u.status] || MUTED, fontFamily: "'DM Sans'", fontSize: 10, fontWeight: 600 }}>
                      {u.status || 'active'}
                    </span>
                    <button onClick={() => openInspector(u)} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${G}`, background: 'rgba(201,168,76,0.08)', color: G, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                      🔍 Inspecionar
                    </button>
                    <button onClick={() => setSelected(selected === u.id ? null : u.id)} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                      Acções
                    </button>
                  </div>
                </div>

                {selected === u.id && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {u.status !== 'active' && (
                      <button onClick={() => handleAction(u.id, 'activate')} style={{ padding: '8px 12px', borderRadius: 8, border: 'none', background: GREEN, color: '#fff', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>✅ Reactivar</button>
                    )}
                    {u.status === 'active' && (
                      <button onClick={() => handleAction(u.id, 'warn')} style={{ padding: '8px 12px', borderRadius: 8, border: 'none', background: G, color: '#000', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>⚠️ Avisar</button>
                    )}
                    {u.status !== 'suspended' && u.status !== 'banned' && (
                      <button onClick={() => handleAction(u.id, 'suspend')} style={{ padding: '8px 12px', borderRadius: 8, border: 'none', background: '#F59E0B', color: '#000', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>🔒 Suspender</button>
                    )}
                    {u.status !== 'banned' && (
                      <button onClick={() => { if (confirm(`Banir ${u.email}?`)) handleAction(u.id, 'ban') }} style={{ padding: '8px 12px', borderRadius: 8, border: 'none', background: RED, color: '#fff', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>🚫 Banir</button>
                    )}
                  </div>
                )}
              </div>
            ))
          }
        </div>

        {/* ── User Inspector Panel (Admin User Mgmt doc CH8-12) ────── */}
        {inspecting && (
          <div onClick={() => setInspecting(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}>
            <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxHeight: '88vh', overflowY: 'auto', background: '#0D0D0D', borderRadius: '18px 18px 0 0', border: `1px solid ${BORDER}`, padding: '18px 16px calc(24px + env(safe-area-inset-bottom))' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div>
                  <h2 style={{ fontFamily: "'Playfair Display'", fontSize: 19, fontWeight: 700, color: TEXT, margin: 0 }}>{inspecting.email}</h2>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: '2px 0 0' }}>ID {inspecting.id} · abertura registada em auditoria</p>
                </div>
                <button onClick={() => setInspecting(null)} style={{ width: 32, height: 32, borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontSize: 16, cursor: 'pointer' }}>✕</button>
              </div>

              {!inspector ? <p style={{ fontFamily: "'DM Sans'", color: MUTED, fontSize: 13 }}>A carregar...</p> : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {/* Identity + ladder + risk */}
                  <div style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: 14 }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                      <span style={{ padding: '3px 10px', borderRadius: 6, background: `${inspector.identity.lifecycle === 'active' ? GREEN : RED}20`, color: inspector.identity.lifecycle === 'active' ? GREEN : RED, fontFamily: "'DM Sans'", fontSize: 11, fontWeight: 600 }}>{inspector.identity.lifecycle}</span>
                      <span style={{ padding: '3px 10px', borderRadius: 6, background: `${G}20`, color: G, fontFamily: "'DM Sans'", fontSize: 11 }}>{LADDER_LABELS[inspector.verification_ladder.level]}</span>
                      <span style={{ padding: '3px 10px', borderRadius: 6, background: `${RISK_COLORS[inspector.risk.badge]}20`, color: RISK_COLORS[inspector.risk.badge], fontFamily: "'DM Sans'", fontSize: 11, fontWeight: 600 }}>risco: {inspector.risk.badge}</span>
                      <span style={{ padding: '3px 10px', borderRadius: 6, background: '#1E1E1E', color: MUTED, fontFamily: "'DM Sans'", fontSize: 11 }}>KYC: {inspector.identity.kyc_status}</span>
                    </div>
                    {inspector.risk.factors.length > 0 && (
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: '#F59E0B', margin: 0 }}>⚠ {inspector.risk.factors.join(' · ')}</p>
                    )}
                  </div>

                  {/* Last sign-ons */}
                  <Section title={`Últimos acessos (${inspector.last_sign_ons.length})`}>
                    {inspector.last_sign_ons.length === 0 ? <Empty text="Sem registos de login" /> :
                      inspector.last_sign_ons.slice(0, 5).map((s, i) => (
                        <Row key={i} left={new Date(s.at).toLocaleString('pt-AO')} right={`${s.ip || '—'} · ${s.device || 'dispositivo desconhecido'}`} />
                      ))}
                  </Section>

                  {/* Active sessions */}
                  <Section title={`Sessões activas (${inspector.sessions.length})`}>
                    {inspector.sessions.length === 0 ? <Empty text="Nenhuma sessão activa" /> :
                      inspector.sessions.map(s => (
                        <Row key={s.session_id} left={`${s.device || 'dispositivo'} · ${s.ip || '—'}`} right={`${Math.floor(s.duration_seconds / 60)} min activa · idle ${Math.floor(s.idle_seconds / 60)} min`} />
                      ))}
                  </Section>

                  {/* Devices */}
                  <Section title={`Dispositivos (${inspector.devices.length})`}>
                    {inspector.devices.length === 0 ? <Empty text="Sem fingerprints registados" /> :
                      inspector.devices.map((d, i) => (
                        <Row key={i} left={`${d.platform || 'desconhecido'} · ${d.fingerprint}…`} right={d.shared_with_users > 0 ? `⚠ partilhado com ${d.shared_with_users} conta(s)` : 'exclusivo desta conta'} />
                      ))}
                  </Section>

                  {/* Access gates */}
                  <Section title="Acessos e capacidades">
                    {Object.entries(inspector.access).filter(([cap]) => cap !== 'restriction').map(([cap, g]) => (
                      <Row key={cap} left={cap.replace('can_', 'pode ').replace('_', ' ')} right={g.enabled ? '✅' : `❌ ${g.reason}`} />
                    ))}
                  </Section>

                  {/* Graduated restrictions (CH5) */}
                  <Section title="Restrições (sem suspender)">
                    {['selling', 'withdrawal', 'messaging'].map(k => {
                      const on = inspector.access.restriction?.[k]
                      const LABEL = { selling: 'Vender', withdrawal: 'Levantar', messaging: 'Mensagens' }
                      return (
                        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED }}>{LABEL[k]}</span>
                          <button onClick={() => toggleRestriction(k)} style={{ padding: '4px 10px', borderRadius: 6, border: `1px solid ${on ? RED : BORDER}`, background: on ? 'rgba(239,68,68,0.12)' : 'none', color: on ? RED : MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                            {on ? '🚫 Restrito' : 'Permitido'}
                          </button>
                        </div>
                      )
                    })}
                    {inspector.access.restriction?.reason && (
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 10, color: MUTED, margin: '4px 0 0' }}>Motivo: {inspector.access.restriction.reason}</p>
                    )}
                  </Section>

                  {/* History timeline */}
                  <Section title="Histórico (utilizador + admins)">
                    {inspector.history.slice(0, 12).map((h, i) => (
                      <Row key={i} left={`${new Date(h.at).toLocaleString('pt-AO')} · ${h.actor}`} right={h.action} />
                    ))}
                  </Section>

                  {/* Security actions */}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button disabled={inspBusy} onClick={terminateSessions} style={{ flex: 1, minWidth: 150, padding: 12, borderRadius: 10, border: 'none', background: '#F59E0B', color: '#000', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                      🔐 Terminar sessões (re-auth)
                    </button>
                    <button disabled={inspBusy} onClick={triggerPasswordReset} style={{ flex: 1, minWidth: 150, padding: 12, borderRadius: 10, border: `1px solid ${BORDER}`, background: CARD, color: TEXT, fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                      ✉️ Enviar reset de password
                    </button>
                    <button disabled={inspBusy} onClick={impersonate} style={{ flex: 1, minWidth: 150, padding: 12, borderRadius: 10, border: '1px solid #7C3AED', background: 'rgba(124,58,237,0.12)', color: '#A78BFA', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                      👁️ Ver como utilizador
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: 14 }}>
      <p style={{ fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, color: TEXT, margin: '0 0 8px' }}>{title}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</div>
    </div>
  )
}

function Row({ left, right }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
      <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, flexShrink: 0 }}>{left}</span>
      <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: TEXT, textAlign: 'right' }}>{right}</span>
    </div>
  )
}

function Empty({ text }) {
  return <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED }}>{text}</span>
}
