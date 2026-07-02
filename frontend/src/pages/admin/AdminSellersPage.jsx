import { useState, useEffect } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'
import { asList } from '@/lib/asList'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444', BLUE = '#3B82F6'

const STATUS_COLORS = { pending: G, approved: GREEN, rejected: RED, suspended: RED }
const STATUS_LABELS = { pending: 'Pendente', approved: 'Aprovado', rejected: 'Rejeitado', suspended: 'Suspenso' }

export default function AdminSellersPage() {
  const [sellers, setSellers] = useState([])
  const [verifications, setVerifications] = useState([])
  const [tab, setTab] = useState('verifications')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      client.get('/api/v1/admin-api/sellers/'),
      client.get('/api/v1/verification/admin/'),
    ]).then(([sellersRes, verRes]) => {
      if (sellersRes.status === 'fulfilled') setSellers(asList(sellersRes.value.data))
      if (verRes.status === 'fulfilled') setVerifications(asList(verRes.value.data))
    }).finally(() => setLoading(false))
  }, [])

  const handleVerification = async (id, action, notes = '') => {
    try {
      await client.post(`/api/v1/verification/admin/${id}/action/`, { action, notes })
      setVerifications(prev => prev.map(v => v.id === id ? { ...v, status: action === 'approve' ? 'approved' : 'rejected' } : v))
      showToast(action === 'approve' ? 'Vendedor aprovado!' : 'Verificação rejeitada')
    } catch { showToast('Erro ao processar', 'error') }
  }

  const handleSellerAction = async (userId, action) => {
    try {
      await client.post(`/api/v1/admin-api/users/${userId}/action/`, { action })
      setSellers(prev => prev.map(s => s.id === userId ? { ...s, status: action } : s))
      showToast(`Vendedor ${action === 'suspend' ? 'suspenso' : 'reactivado'}`)
    } catch { showToast('Erro ao processar', 'error') }
  }

  const filtered = sellers.filter(s => !search || s.email?.toLowerCase().includes(search.toLowerCase()) || s.store_name?.toLowerCase().includes(search.toLowerCase()))
  const pendingVer = verifications.filter(v => v.status === 'pending')

  return (
    <AdminLayout title="Vendedores">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, fontFamily: "'DM Sans'", fontSize: 13 }}>{toast.msg}</div>}

        <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 16px' }}>Gestão de Vendedores</h1>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {[
            { key: 'verifications', label: `Verificações ${pendingVer.length > 0 ? `(${pendingVer.length})` : ''}` },
            { key: 'sellers', label: `Todos (${sellers.length})` },
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{ padding: '8px 14px', borderRadius: 10, border: `1.5px solid ${tab === t.key ? G : BORDER}`, background: tab === t.key ? 'rgba(201,168,76,0.1)' : 'none', color: tab === t.key ? G : MUTED, fontFamily: "'DM Sans'", fontSize: 12, fontWeight: tab === t.key ? 600 : 400, cursor: 'pointer' }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Verifications tab */}
        {tab === 'verifications' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED, fontSize: 13 }}>A carregar...</p> :
              verifications.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 15, color: GREEN }}>✅ Nenhuma verificação pendente</p>
                </div>
              ) : verifications.map(v => (
                <div key={v.id} style={{ background: CARD, borderRadius: 14, border: `1.5px solid ${v.status === 'pending' ? 'rgba(201,168,76,0.3)' : BORDER}`, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 14, fontWeight: 600, color: TEXT, margin: '0 0 2px' }}>{v.seller_email || v.seller?.email}</p>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: 0 }}>
                        Submetido: {v.submitted_at ? new Date(v.submitted_at).toLocaleDateString('pt-AO') : 'N/A'}
                      </p>
                    </div>
                    <span style={{ padding: '3px 10px', borderRadius: 6, background: `${STATUS_COLORS[v.status] || MUTED}20`, color: STATUS_COLORS[v.status] || MUTED, fontFamily: "'DM Sans'", fontSize: 11, fontWeight: 600 }}>
                      {STATUS_LABELS[v.status] || v.status}
                    </span>
                  </div>

                  {/* Identity details */}
                  <div style={{ background: '#0d0d0d', border: `1px solid ${BORDER}`, borderRadius: 10, padding: 12, marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED }}>Nº do BI / Identidade</span>
                      <span style={{ fontFamily: "'DM Sans'", fontSize: 13, color: TEXT, fontWeight: 600 }}>{v.id_number || '—'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED }}>Validade</span>
                      <span style={{ fontFamily: "'DM Sans'", fontSize: 13, color: v.is_id_expired ? RED : TEXT }}>
                        {v.id_expiry_date ? new Date(v.id_expiry_date).toLocaleDateString('pt-AO') : '—'}{v.is_id_expired ? ' · expirado' : ''}
                      </span>
                    </div>
                    {v.id_validation_error && (
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: RED, margin: '6px 0 0' }}>⚠ {v.id_validation_error}</p>
                    )}
                  </div>

                  {/* Documents + selfie */}
                  <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                    {v.selfie_url && (
                      <a href={v.selfie_url} target="_blank" rel="noreferrer">
                        <img src={v.selfie_url} alt="selfie" style={{ width: 52, height: 52, borderRadius: 8, objectFit: 'cover', border: `1px solid ${BORDER}` }} />
                      </a>
                    )}
                    {v.id_document_url && (
                      <a href={v.id_document_url} target="_blank" rel="noreferrer" style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${BORDER}`, color: BLUE, fontFamily: "'DM Sans'", fontSize: 12, textDecoration: 'none' }}>📄 BI (frente)</a>
                    )}
                    {v.id_document_back_url && (
                      <a href={v.id_document_back_url} target="_blank" rel="noreferrer" style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${BORDER}`, color: BLUE, fontFamily: "'DM Sans'", fontSize: 12, textDecoration: 'none' }}>📄 BI (verso)</a>
                    )}
                    {!v.id_document_url && !v.selfie_url && (
                      <span style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED }}>Sem documentos carregados</span>
                    )}
                  </div>

                  {v.status === 'pending' && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => handleVerification(v.id, 'approve')} style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: GREEN, color: '#fff', fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                        ✅ Aprovar
                      </button>
                      <button onClick={() => handleVerification(v.id, 'reject')} style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: RED, color: '#fff', fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                        ❌ Rejeitar
                      </button>
                    </div>
                  )}
                </div>
              ))
            }
          </div>
        )}

        {/* All sellers tab */}
        {tab === 'sellers' && (
          <div>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar por email ou loja..." style={{ width: '100%', padding: '11px 14px', background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, color: TEXT, fontFamily: "'DM Sans'", fontSize: 13, outline: 'none', marginBottom: 12, boxSizing: 'border-box' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filtered.map(s => (
                <div key={s.id} style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: '13px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 500, color: TEXT, margin: '0 0 2px' }}>{s.store_name || s.email}</p>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: 0 }}>{s.email} · {s.total_sales || 0} vendas</p>
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, background: `${STATUS_COLORS[s.status] || MUTED}20`, color: STATUS_COLORS[s.status] || MUTED, fontFamily: "'DM Sans'", fontSize: 10, fontWeight: 600 }}>
                      {STATUS_LABELS[s.status] || 'Activo'}
                    </span>
                    <button onClick={() => handleSellerAction(s.id, s.status === 'suspended' ? 'activate' : 'suspend')} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: s.status === 'suspended' ? GREEN : RED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                      {s.status === 'suspended' ? 'Reactivar' : 'Suspender'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
