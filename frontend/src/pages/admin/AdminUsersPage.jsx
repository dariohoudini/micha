import { useState, useEffect } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'
import { asList } from '@/lib/asList'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444'
const STATUS_COLORS = { active: GREEN, warned: G, suspended: RED, banned: RED }

export default function AdminUsersPage() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [toast, setToast] = useState(null)
  const [selected, setSelected] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

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
      </div>
    </AdminLayout>
  )
}
