import { useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import { formatPrice } from '@/components/buyer/mockData'

const MOCK_PRODUCTS = [
  { id: 1, name: 'Vestido Capulana Premium', seller: 'Moda Luanda', category: 'Moda', price: 8500, status: 'approved', reports: 0, sales: 34, image_color: '#8B4513', created: '10 Jan 2026' },
  { id: 2, name: 'Smartphone Xiaomi Note 14', seller: 'TechShop Angola', category: 'Tecnologia', price: 145000, status: 'pending', reports: 0, sales: 0, image_color: '#1a1a2e', created: '13 Abr 2026' },
  { id: 3, name: 'Perfume "Original"', seller: 'Beauty Store', category: 'Beleza', price: 5000, status: 'reported', reports: 3, sales: 12, image_color: '#2d3748', created: '05 Mar 2026', reportReason: 'Produto potencialmente falsificado' },
  { id: 4, name: 'Colar de Ouro 18K', seller: 'Joias Angola', category: 'Acessórios', price: 350000, status: 'pending', reports: 0, sales: 0, image_color: '#B8860B', created: '12 Abr 2026' },
  { id: 5, name: 'Kit Medicamentos', seller: 'Farmácia Online', category: 'Saúde', price: 12000, status: 'rejected', reports: 5, sales: 0, image_color: '#2d4a22', created: '01 Abr 2026', reportReason: 'Venda de medicamentos não autorizada' },
  { id: 6, name: 'Ténis Nike Air Max Originais', seller: 'SportZone AO', category: 'Desporto', price: 52000, status: 'approved', reports: 0, sales: 89, image_color: '#1e3a5f', created: '15 Fev 2026' },
]

const STATUS_CONFIG = {
  approved: { label: 'Aprovado',  color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
  pending:  { label: 'Pendente',  color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  reported: { label: 'Reportado', color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
  rejected: { label: 'Rejeitado', color: '#6b7280', bg: 'rgba(107,114,128,0.1)' },
}

export default function AdminProductsPage() {
  const [products, setProducts] = useState(MOCK_PRODUCTS)
  const [filter, setFilter] = useState('pending')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const approveProduct = (id) => {
    setProducts(prev => prev.map(p => p.id === id ? { ...p, status: 'approved', reports: 0 } : p))
    showToast('Produto aprovado e publicado!')
    setSelected(null)
  }

  const rejectProduct = (id) => {
    setProducts(prev => prev.map(p => p.id === id ? { ...p, status: 'rejected' } : p))
    showToast('Produto rejeitado e removido.', 'error')
    setSelected(null)
  }

  const filtered = products.filter(p => {
    const matchFilter = filter === 'all' || p.status === filter
    const matchSearch = !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.seller.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  return (
    <AdminLayout title="Produtos">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>{toast.msg}</div>
      )}

      {selected && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) setSelected(null) }}>
          <div style={{ background: ADMIN_COLORS.card, borderRadius: '20px 20px 0 0', border: `1px solid ${ADMIN_COLORS.border}`, padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: ADMIN_COLORS.border, margin: '0 auto 20px' }} />
            <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
              <div style={{ width: 60, height: 60, borderRadius: 12, background: selected.image_color, flexShrink: 0 }} />
              <div>
                <p style={{ fontSize: 15, fontWeight: 600, color: ADMIN_COLORS.text, marginBottom: 2 }}>{selected.name}</p>
                <p style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>{selected.seller} · {selected.category}</p>
                <p style={{ fontSize: 14, fontWeight: 700, color: '#C9A84C', marginTop: 4 }}>{formatPrice(selected.price)}</p>
              </div>
            </div>
            {selected.reportReason && (
              <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: '10px 14px', marginBottom: 16 }}>
                <p style={{ fontSize: 12, color: '#ef4444', fontWeight: 600, marginBottom: 2 }}>⚠️ {selected.reports} reporte(s)</p>
                <p style={{ fontSize: 12, color: ADMIN_COLORS.text }}>{selected.reportReason}</p>
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {selected.status !== 'approved' && (
                <button onClick={() => approveProduct(selected.id)}
                  style={{ padding: '14px', borderRadius: 12, border: 'none', background: '#10b981', fontSize: 14, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
                  ✓ Aprovar produto
                </button>
              )}
              {selected.status !== 'rejected' && (
                <button onClick={() => rejectProduct(selected.id)}
                  style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.1)', fontSize: 14, fontWeight: 500, color: '#ef4444', cursor: 'pointer' }}>
                  ✗ Remover produto
                </button>
              )}
              <button onClick={() => setSelected(null)}
                style={{ padding: '14px', borderRadius: 12, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 14, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[
            { l: 'Total', v: products.length, c: ADMIN_COLORS.text },
            { l: 'Pendentes', v: products.filter(p => p.status === 'pending').length, c: '#f59e0b' },
            { l: 'Reportados', v: products.filter(p => p.status === 'reported').length, c: '#ef4444' },
            { l: 'Aprovados', v: products.filter(p => p.status === 'approved').length, c: '#10b981' },
          ].map(s => (
            <div key={s.l} style={{ flex: 1, background: ADMIN_COLORS.card, borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, padding: '8px 6px', textAlign: 'center' }}>
              <p style={{ fontSize: 16, fontWeight: 700, color: s.c }}>{s.v}</p>
              <p style={{ fontSize: 9, color: ADMIN_COLORS.muted, marginTop: 1 }}>{s.l}</p>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '10px 14px', marginBottom: 10 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar produto ou vendedor..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: ADMIN_COLORS.text }} />
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {[{ v: 'all', l: 'Todos' }, { v: 'pending', l: 'Pendentes' }, { v: 'reported', l: 'Reportados' }, { v: 'approved', l: 'Aprovados' }, { v: 'rejected', l: 'Rejeitados' }].map(f => (
            <button key={f.v} onClick={() => setFilter(f.v)}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#6366f1' : ADMIN_COLORS.border}`, background: filter === f.v ? 'rgba(99,102,241,0.1)' : 'transparent', fontSize: 11, color: filter === f.v ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(product => {
            const status = STATUS_CONFIG[product.status]
            return (
              <div key={product.id} style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${product.status === 'reported' ? 'rgba(239,68,68,0.3)' : ADMIN_COLORS.border}`, padding: 14 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <div style={{ width: 56, height: 56, borderRadius: 10, background: product.image_color, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                    </svg>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                      <p style={{ fontSize: 14, fontWeight: 600, color: ADMIN_COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, marginRight: 8 }}>{product.name}</p>
                      <span style={{ fontSize: 10, fontWeight: 600, color: status.color, background: status.bg, padding: '2px 8px', borderRadius: 20, flexShrink: 0 }}>{status.label}</span>
                    </div>
                    <p style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 4 }}>{product.seller} · {product.category}</p>
                    <div style={{ display: 'flex', gap: 10 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(product.price)}</span>
                      {product.reports > 0 && <span style={{ fontSize: 11, color: '#ef4444', fontWeight: 600 }}>⚠️ {product.reports} reporte(s)</span>}
                      {product.sales > 0 && <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>🛒 {product.sales} vendas</span>}
                    </div>
                    {product.reportReason && (
                      <p style={{ fontSize: 11, color: '#ef4444', marginTop: 4 }}>{product.reportReason}</p>
                    )}
                  </div>
                </div>
                <button onClick={() => setSelected(product)}
                  style={{ width: '100%', padding: '10px 0', borderRadius: 10, marginTop: 12, border: `1px solid ${product.status === 'pending' || product.status === 'reported' ? 'rgba(99,102,241,0.3)' : ADMIN_COLORS.border}`, background: product.status === 'pending' || product.status === 'reported' ? 'rgba(99,102,241,0.08)' : 'transparent', fontSize: 13, fontWeight: 500, color: product.status === 'pending' || product.status === 'reported' ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer' }}>
                  {product.status === 'pending' ? 'Moderar produto' : product.status === 'reported' ? '⚠️ Rever denúncia' : 'Ver detalhes'}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </AdminLayout>
  )
}
