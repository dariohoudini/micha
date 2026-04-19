import { useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import { formatPrice } from '@/components/buyer/mockData'

const MOCK_SELLERS = [
  { id: 1, store: 'Moda Luanda Premium', owner: 'Maria Santos', email: 'maria@yahoo.com', category: 'Moda', province: 'Luanda', status: 'pending', products: 0, sales: 0, revenue: 0, joined: '12 Abr 2026', nif: '123456789', verified: false },
  { id: 2, store: 'TechShop Angola', owner: 'Carlos Mendes', email: 'carlos@gmail.com', category: 'Tecnologia', province: 'Luanda', status: 'pending', products: 0, sales: 0, revenue: 0, joined: '11 Abr 2026', nif: '987654321', verified: false },
  { id: 3, store: 'Moda Benguela', owner: 'Ana Costa', email: 'ana@hotmail.com', category: 'Moda', province: 'Benguela', status: 'pending', products: 0, sales: 0, revenue: 0, joined: '10 Abr 2026', nif: '', verified: false },
  { id: 4, store: 'Beauty Angola', owner: 'Lucia Ferreira', email: 'lucia@gmail.com', category: 'Beleza', province: 'Luanda', status: 'approved', products: 28, sales: 156, revenue: 845000, joined: '15 Jan 2026', nif: '456789123', verified: true },
  { id: 5, store: 'SportZone AO', owner: 'Pedro Neto', email: 'pedro@gmail.com', category: 'Desporto', province: 'Luanda', status: 'approved', products: 45, sales: 289, revenue: 2340000, joined: '03 Fev 2026', nif: '789123456', verified: true },
  { id: 6, store: 'Casa & Lar AO', owner: 'João Silva', email: 'joao@gmail.com', category: 'Casa & Jardim', province: 'Huambo', status: 'suspended', products: 12, sales: 34, revenue: 156000, joined: '20 Mar 2026', nif: '321654987', verified: true },
]

const STATUS_CONFIG = {
  pending:   { label: 'Pendente',   color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  approved:  { label: 'Aprovado',  color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
  suspended: { label: 'Suspenso',  color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
  rejected:  { label: 'Rejeitado', color: '#6b7280', bg: 'rgba(107,114,128,0.1)' },
}

export default function AdminSellersPage() {
  const [sellers, setSellers] = useState(MOCK_SELLERS)
  const [filter, setFilter] = useState('pending')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [showReject, setShowReject] = useState(false)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const approveSeller = (id) => {
    setSellers(prev => prev.map(s => s.id === id ? { ...s, status: 'approved', verified: true } : s))
    showToast('Vendedor aprovado e notificado!')
    setSelected(null)
  }

  const rejectSeller = (id) => {
    setSellers(prev => prev.map(s => s.id === id ? { ...s, status: 'rejected' } : s))
    showToast('Vendedor rejeitado.', 'error')
    setSelected(null)
    setShowReject(false)
    setRejectReason('')
  }

  const suspendSeller = (id) => {
    setSellers(prev => prev.map(s => s.id === id ? { ...s, status: 'suspended' } : s))
    showToast('Vendedor suspenso.')
    setSelected(null)
  }

  const reactivateSeller = (id) => {
    setSellers(prev => prev.map(s => s.id === id ? { ...s, status: 'approved' } : s))
    showToast('Vendedor reactivado.')
    setSelected(null)
  }

  const filtered = sellers.filter(s => {
    const matchFilter = filter === 'all' || s.status === filter
    const matchSearch = !search || s.store.toLowerCase().includes(search.toLowerCase()) || s.owner.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  const pendingCount = sellers.filter(s => s.status === 'pending').length

  return (
    <AdminLayout title="Vendedores">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>{toast.msg}</div>
      )}

      {/* Action modal */}
      {selected && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) { setSelected(null); setShowReject(false) } }}>
          <div style={{ background: ADMIN_COLORS.card, borderRadius: '20px 20px 0 0', border: `1px solid ${ADMIN_COLORS.border}`, padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: ADMIN_COLORS.border, margin: '0 auto 20px' }} />
            <h3 style={{ fontSize: 17, fontWeight: 700, color: ADMIN_COLORS.text, marginBottom: 2 }}>{selected.store}</h3>
            <p style={{ fontSize: 13, color: ADMIN_COLORS.muted, marginBottom: 6 }}>{selected.owner} · {selected.email}</p>
            <p style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 20 }}>
              {selected.category} · {selected.province} · NIF: {selected.nif || 'Não fornecido'}
            </p>

            {!showReject ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {selected.status === 'pending' && <>
                  <button onClick={() => approveSeller(selected.id)}
                    style={{ padding: '14px', borderRadius: 12, border: 'none', background: '#10b981', fontSize: 14, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
                    ✓ Aprovar vendedor
                  </button>
                  <button onClick={() => setShowReject(true)}
                    style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.1)', fontSize: 14, fontWeight: 500, color: '#ef4444', cursor: 'pointer' }}>
                    ✗ Rejeitar candidatura
                  </button>
                </>}
                {selected.status === 'approved' && (
                  <button onClick={() => suspendSeller(selected.id)}
                    style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.1)', fontSize: 14, fontWeight: 500, color: '#f59e0b', cursor: 'pointer' }}>
                    ⏸ Suspender loja
                  </button>
                )}
                {selected.status === 'suspended' && (
                  <button onClick={() => reactivateSeller(selected.id)}
                    style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(16,185,129,0.3)', background: 'rgba(16,185,129,0.1)', fontSize: 14, fontWeight: 500, color: '#10b981', cursor: 'pointer' }}>
                    ✓ Reactivar loja
                  </button>
                )}
                <button onClick={() => setSelected(null)}
                  style={{ padding: '14px', borderRadius: 12, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 14, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                  Cancelar
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <label style={{ fontSize: 12, color: ADMIN_COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Motivo da rejeição</label>
                <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)}
                  placeholder="Ex: Documentação incompleta. NIF não fornecido. Categoria não suportada..."
                  style={{ background: ADMIN_COLORS.surface, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '12px 14px', color: ADMIN_COLORS.text, fontSize: 13, lineHeight: 1.6, resize: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif" }}
                  rows={3} />
                <button onClick={() => rejectSeller(selected.id)}
                  style={{ padding: '14px', borderRadius: 12, border: 'none', background: '#ef4444', fontSize: 14, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
                  Confirmar rejeição
                </button>
                <button onClick={() => setShowReject(false)}
                  style={{ padding: '14px', borderRadius: 12, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 14, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                  Voltar
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {/* Stats */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[
            { l: 'Total', v: sellers.length, c: ADMIN_COLORS.text },
            { l: 'Pendentes', v: sellers.filter(s => s.status === 'pending').length, c: '#f59e0b' },
            { l: 'Aprovados', v: sellers.filter(s => s.status === 'approved').length, c: '#10b981' },
            { l: 'Suspensos', v: sellers.filter(s => s.status === 'suspended').length, c: '#ef4444' },
          ].map(s => (
            <div key={s.l} style={{ flex: 1, background: ADMIN_COLORS.card, borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, padding: '8px 6px', textAlign: 'center' }}>
              <p style={{ fontSize: 16, fontWeight: 700, color: s.c }}>{s.v}</p>
              <p style={{ fontSize: 9, color: ADMIN_COLORS.muted, marginTop: 1 }}>{s.l}</p>
            </div>
          ))}
        </div>

        {/* Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '10px 14px', marginBottom: 10 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar loja ou proprietário..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: ADMIN_COLORS.text }} />
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {[{ v: 'all', l: 'Todos' }, { v: 'pending', l: `Pendentes (${pendingCount})` }, { v: 'approved', l: 'Aprovados' }, { v: 'suspended', l: 'Suspensos' }, { v: 'rejected', l: 'Rejeitados' }].map(f => (
            <button key={f.v} onClick={() => setFilter(f.v)}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#6366f1' : ADMIN_COLORS.border}`, background: filter === f.v ? 'rgba(99,102,241,0.1)' : 'transparent', fontSize: 11, color: filter === f.v ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer', whiteSpace: 'nowrap' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: ADMIN_COLORS.muted, fontSize: 14 }}>
              Sem vendedores neste estado.
            </div>
          ) : filtered.map(seller => {
            const status = STATUS_CONFIG[seller.status]
            return (
              <div key={seller.id} style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${seller.status === 'pending' ? 'rgba(245,158,11,0.2)' : ADMIN_COLORS.border}`, padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                      <p style={{ fontSize: 14, fontWeight: 600, color: ADMIN_COLORS.text }}>{seller.store}</p>
                      {seller.verified && <svg width="12" height="12" viewBox="0 0 24 24" fill="#6366f1"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                    </div>
                    <p style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>{seller.owner} · {seller.email}</p>
                  </div>
                  <span style={{ fontSize: 10, fontWeight: 600, color: status.color, background: status.bg, padding: '3px 8px', borderRadius: 20, flexShrink: 0, marginLeft: 8 }}>{status.label}</span>
                </div>

                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>📂 {seller.category}</span>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>📍 {seller.province}</span>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>📅 {seller.joined}</span>
                  {seller.nif ? <span style={{ fontSize: 11, color: '#10b981' }}>✓ NIF: {seller.nif}</span> : <span style={{ fontSize: 11, color: '#ef4444' }}>✗ Sem NIF</span>}
                </div>

                {seller.status === 'approved' && (
                  <div style={{ display: 'flex', gap: 12, padding: '8px 0', borderTop: `1px solid ${ADMIN_COLORS.border}`, marginBottom: 10 }}>
                    <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>📦 {seller.products} produtos</span>
                    <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>🛒 {seller.sales} vendas</span>
                    <span style={{ fontSize: 11, color: '#C9A84C' }}>💰 {formatPrice(seller.revenue)}</span>
                  </div>
                )}

                <button onClick={() => setSelected(seller)}
                  style={{ width: '100%', padding: '10px 0', borderRadius: 10, border: `1px solid ${seller.status === 'pending' ? 'rgba(245,158,11,0.3)' : ADMIN_COLORS.border}`, background: seller.status === 'pending' ? 'rgba(245,158,11,0.08)' : 'transparent', fontSize: 13, fontWeight: 500, color: seller.status === 'pending' ? '#f59e0b' : ADMIN_COLORS.text, cursor: 'pointer' }}>
                  {seller.status === 'pending' ? '⚡ Analisar candidatura' : 'Gerir vendedor'}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </AdminLayout>
  )
}
