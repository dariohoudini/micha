import { useState, useEffect, useCallback } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'

export default function AdminUsersPage() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [roleFilter, setRoleFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page })
      if (search) params.set('search', search)
      if (filter !== 'all') params.set('status', filter)
      if (roleFilter !== 'all') params.set('role', roleFilter)

      const res = await client.get(`/api/admin/users/?${params}`)
      setUsers(res.data.results || [])
      setTotal(res.data.total || 0)
      setPages(res.data.pages || 1)
    } catch (err) {
      console.error('Failed to load users:', err)
    } finally {
      setLoading(false)
    }
  }, [page, search, filter, roleFilter])

  useEffect(() => {
    const t = setTimeout(loadUsers, search ? 400 : 0)
    return () => clearTimeout(t)
  }, [loadUsers])

  const handleAction = async (userId, action) => {
    setActionLoading(true)
    try {
      await client.post(`/api/admin/users/${userId}/action/`, { action })
      showToast(action === 'suspend' ? 'Utilizador suspenso.' : 'Utilizador reactivado.')
      setSelected(null)
      loadUsers()
    } catch {
      showToast('Acção falhou.', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <AdminLayout title="Utilizadores">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      {/* Action modal */}
      {selected && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) setSelected(null) }}>
          <div style={{ background: ADMIN_COLORS.card, borderRadius: '20px 20px 0 0', border: `1px solid ${ADMIN_COLORS.border}`, padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: ADMIN_COLORS.border, margin: '0 auto 20px' }} />
            <h3 style={{ fontSize: 17, fontWeight: 700, color: ADMIN_COLORS.text, marginBottom: 4 }}>{selected.username || selected.email}</h3>
            <p style={{ fontSize: 13, color: ADMIN_COLORS.muted, marginBottom: 20 }}>{selected.email}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {!selected.is_active ? (
                <button onClick={() => handleAction(selected.id, 'activate')} disabled={actionLoading}
                  style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(16,185,129,0.3)', background: 'rgba(16,185,129,0.1)', fontSize: 14, fontWeight: 500, color: '#10b981', cursor: 'pointer' }}>
                  ✓ Reactivar conta
                </button>
              ) : (
                <button onClick={() => handleAction(selected.id, 'suspend')} disabled={actionLoading}
                  style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.1)', fontSize: 14, fontWeight: 500, color: '#f59e0b', cursor: 'pointer' }}>
                  ⏸ Suspender conta
                </button>
              )}
              <button onClick={() => setSelected(null)}
                style={{ padding: '14px', borderRadius: 12, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 14, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {/* Stats bar */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[{ l: 'Total', v: total }, { l: 'Página', v: `${page}/${pages}` }].map(s => (
            <div key={s.l} style={{ flex: 1, background: ADMIN_COLORS.card, borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, padding: '8px 10px', textAlign: 'center' }}>
              <p style={{ fontSize: 15, fontWeight: 700, color: ADMIN_COLORS.text }}>{s.v}</p>
              <p style={{ fontSize: 10, color: ADMIN_COLORS.muted }}>{s.l}</p>
            </div>
          ))}
        </div>

        {/* Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '10px 14px', marginBottom: 10 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder="Pesquisar email ou username..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: ADMIN_COLORS.text }} />
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {[{ v: 'all', l: 'Todos' }, { v: 'active', l: 'Activos' }, { v: 'suspended', l: 'Suspensos' }].map(f => (
            <button key={f.v} onClick={() => { setFilter(f.v); setPage(1) }}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#6366f1' : ADMIN_COLORS.border}`, background: filter === f.v ? 'rgba(99,102,241,0.1)' : 'transparent', fontSize: 11, color: filter === f.v ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
          <div style={{ width: 1, background: ADMIN_COLORS.border }} />
          {[{ v: 'all', l: 'Todos' }, { v: 'buyer', l: 'Compradores' }, { v: 'seller', l: 'Vendedores' }].map(f => (
            <button key={f.v} onClick={() => { setRoleFilter(f.v); setPage(1) }}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${roleFilter === f.v ? '#f59e0b' : ADMIN_COLORS.border}`, background: roleFilter === f.v ? 'rgba(245,158,11,0.1)' : 'transparent', fontSize: 11, color: roleFilter === f.v ? '#f59e0b' : ADMIN_COLORS.muted, cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #6366f1', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {users.length === 0 ? (
              <p style={{ textAlign: 'center', color: ADMIN_COLORS.muted, fontSize: 14, padding: '40px 0' }}>Sem utilizadores encontrados.</p>
            ) : users.map(user => (
              <div key={user.id} style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${ADMIN_COLORS.border}`, padding: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1, #4f46e5)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <span style={{ fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>{(user.username || user.email)[0].toUpperCase()}</span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                      <p style={{ fontSize: 14, fontWeight: 600, color: ADMIN_COLORS.text }}>{user.username || user.email.split('@')[0]}</p>
                      {!user.is_active && <span style={{ fontSize: 10, color: '#f59e0b', background: 'rgba(245,158,11,0.1)', padding: '1px 6px', borderRadius: 10 }}>Suspenso</span>}
                      {user.is_seller && <span style={{ fontSize: 10, color: '#f59e0b', background: 'rgba(245,158,11,0.1)', padding: '1px 6px', borderRadius: 10 }}>Vendedor</span>}
                      {user.is_staff && <span style={{ fontSize: 10, color: '#818cf8', background: 'rgba(99,102,241,0.1)', padding: '1px 6px', borderRadius: 10 }}>Admin</span>}
                    </div>
                    <p style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>{user.email}</p>
                    <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginTop: 2 }}>
                      Registado: {new Date(user.date_joined).toLocaleDateString('pt-AO')}
                    </p>
                  </div>
                  <button onClick={() => setSelected(user)}
                    style={{ padding: '7px 12px', borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 12, color: ADMIN_COLORS.text, cursor: 'pointer', flexShrink: 0 }}>
                    Gerir
                  </button>
                </div>
              </div>
            ))}

            {/* Pagination */}
            {pages > 1 && (
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', paddingTop: 8 }}>
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  style={{ padding: '8px 16px', borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 13, color: page === 1 ? ADMIN_COLORS.muted : ADMIN_COLORS.text, cursor: page === 1 ? 'not-allowed' : 'pointer' }}>
                  ← Anterior
                </button>
                <span style={{ fontSize: 13, color: ADMIN_COLORS.muted, display: 'flex', alignItems: 'center' }}>
                  {page} / {pages}
                </span>
                <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page === pages}
                  style={{ padding: '8px 16px', borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 13, color: page === pages ? ADMIN_COLORS.muted : ADMIN_COLORS.text, cursor: page === pages ? 'not-allowed' : 'pointer' }}>
                  Próxima →
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
