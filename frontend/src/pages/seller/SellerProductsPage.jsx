import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import { formatPrice } from '@/components/buyer/mockData'

const STATUS_CONFIG = {
  active:        { label: 'Activo',    color: '#059669', bg: 'rgba(5,150,105,0.1)' },
  inactive:      { label: 'Inactivo', color: '#9A9A9A', bg: 'rgba(154,154,154,0.1)' },
  out_of_stock:  { label: 'Esgotado', color: '#dc2626', bg: 'rgba(220,38,38,0.1)' },
  pending:       { label: 'Pendente', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
}

const INITIAL_PRODUCTS = [
  { id: '1', name: 'Vestido Capulana Premium', price: 8500, original_price: 12000, stock: 24, sales: 34, views: 892, image_color: '#8B4513', status: 'active', category: 'Moda' },
  { id: '2', name: 'Colar de Missangas Tradicional', price: 4500, original_price: null, stock: 50, sales: 28, views: 654, image_color: '#1a1a2e', status: 'active', category: 'Acessórios' },
  { id: '3', name: 'Bolsa de Couro Genuíno', price: 28000, original_price: 35000, stock: 3, sales: 12, views: 421, image_color: '#5c3d2e', status: 'active', category: 'Moda' },
  { id: '4', name: 'Pulseira de Prata Angola', price: 6500, original_price: null, stock: 0, sales: 8, views: 234, image_color: '#2d3748', status: 'out_of_stock', category: 'Acessórios' },
]

export default function SellerProductsPage() {
  const navigate = useNavigate()
  const [products, setProducts] = useState(INITIAL_PRODUCTS)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState(null)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const toggleStatus = (id) => {
    setProducts(prev => prev.map(p => {
      if (p.id !== id) return p
      const next = p.status === 'active' ? 'inactive' : 'active'
      return { ...p, status: next }
    }))
    showToast('Estado do produto actualizado.')
  }

  const deleteProduct = (id) => {
    setProducts(prev => prev.filter(p => p.id !== id))
    setDeleteConfirm(null)
    showToast('Produto eliminado.', 'error')
  }

  const filtered = products.filter(p => {
    const matchFilter = filter === 'all' || p.status === filter
    const matchSearch = !search || p.name.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  const stats = {
    total: products.length,
    active: products.filter(p => p.status === 'active').length,
    outOfStock: products.filter(p => p.stock === 0).length,
    totalSales: products.reduce((a, p) => a + p.sales, 0),
  }

  return (
    <SellerLayout title="Produtos">
      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteConfirm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 100, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div style={{ background: '#141414', borderRadius: '20px 20px 0 0', border: '1px solid #2A2A2A', padding: '24px 20px 40px', width: '100%', maxWidth: 430 }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A', margin: '0 auto 20px' }} />
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>Eliminar produto?</h3>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', marginBottom: 24, lineHeight: 1.5 }}>
              Esta acção não pode ser desfeita. O produto será removido permanentemente da sua loja.
            </p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setDeleteConfirm(null)} className="btn-secondary" style={{ flex: 1 }}>Cancelar</button>
              <button onClick={() => deleteProduct(deleteConfirm)}
                style={{ flex: 1, padding: '1rem', borderRadius: '1rem', background: '#dc2626', border: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
                Eliminar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Search + Add */}
      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {/* Quick stats */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[
            { label: 'Total', value: stats.total, color: '#FFFFFF' },
            { label: 'Activos', value: stats.active, color: '#059669' },
            { label: 'Esgotados', value: stats.outOfStock, color: '#dc2626' },
            { label: 'Vendas', value: stats.totalSales, color: '#C9A84C' },
          ].map(s => (
            <div key={s.label} style={{ flex: 1, background: '#141414', borderRadius: 10, border: '1px solid #1E1E1E', padding: '8px 6px', textAlign: 'center' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: s.color }}>{s.value}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: '#9A9A9A', marginTop: 1 }}>{s.label}</p>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '10px 14px' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar produtos..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }} />
            {search && <button onClick={() => setSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>}
          </div>
          <button onClick={() => navigate('/seller/product/new')}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', borderRadius: 12, background: '#C9A84C', border: 'none', cursor: 'pointer', flexShrink: 0 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#0A0A0A' }}>Novo</span>
          </button>
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 12 }}>
          {[{ v: 'all', l: 'Todos' }, { v: 'active', l: 'Activos' }, { v: 'inactive', l: 'Inactivos' }, { v: 'out_of_stock', l: 'Esgotados' }].map(tab => (
            <button key={tab.v} onClick={() => setFilter(tab.v)}
              style={{ padding: '6px 14px', borderRadius: 50, flexShrink: 0, border: `1.5px solid ${filter === tab.v ? '#C9A84C' : '#2A2A2A'}`, background: filter === tab.v ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: filter === tab.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {tab.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {filtered.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '50%', gap: 16, padding: '0 32px' }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>
              {search ? `Sem resultados para "${search}"` : 'Sem produtos nesta categoria.'}
            </p>
            <button className="btn-primary" onClick={() => navigate('/seller/product/new')} style={{ width: 'auto', padding: '10px 24px' }}>
              Adicionar produto
            </button>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filtered.map(product => {
              const status = STATUS_CONFIG[product.status] || STATUS_CONFIG.inactive
              const discount = product.original_price ? Math.round((1 - product.price / product.original_price) * 100) : null
              return (
                <div key={product.id} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                    {/* Image */}
                    <div style={{ width: 64, height: 64, borderRadius: 10, background: product.image_color, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                      </svg>
                    </div>

                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, marginRight: 8 }}>{product.name}</p>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: status.color, background: status.bg, padding: '2px 8px', borderRadius: 20, flexShrink: 0 }}>{status.label}</span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 6 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(product.price)}</span>
                        {product.original_price && (
                          <>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', textDecoration: 'line-through' }}>{formatPrice(product.original_price)}</span>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: '#FFFFFF', background: '#dc2626', padding: '1px 5px', borderRadius: 4 }}>-{discount}%</span>
                          </>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: 10 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: product.stock === 0 ? '#dc2626' : product.stock <= 3 ? '#f59e0b' : '#9A9A9A' }}>
                          📦 {product.stock === 0 ? 'Esgotado' : `${product.stock} em stock`}
                        </span>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>🛒 {product.sales} vendas</span>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>👁 {product.views}</span>
                      </div>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div style={{ display: 'flex', gap: 8, marginTop: 12, paddingTop: 12, borderTop: '1px solid #1E1E1E' }}>
                    {/* Toggle active/inactive */}
                    <button onClick={() => toggleStatus(product.id)}
                      style={{
                        flex: 1, padding: '8px 0', borderRadius: 10, cursor: 'pointer',
                        border: `1px solid ${product.status === 'active' ? '#2A2A2A' : 'rgba(5,150,105,0.3)'}`,
                        background: product.status === 'active' ? 'transparent' : 'rgba(5,150,105,0.1)',
                        fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500,
                        color: product.status === 'active' ? '#9A9A9A' : '#059669',
                      }}>
                      {product.status === 'active' ? 'Desactivar' : 'Activar'}
                    </button>

                    {/* Edit */}
                    <button onClick={() => navigate('/seller/product/new')}
                      style={{ flex: 1, padding: '8px 0', borderRadius: 10, cursor: 'pointer', border: '1px solid rgba(201,168,76,0.3)', background: 'rgba(201,168,76,0.08)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#C9A84C' }}>
                      Editar
                    </button>

                    {/* Delete */}
                    <button onClick={() => setDeleteConfirm(product.id)}
                      style={{ width: 36, borderRadius: 10, cursor: 'pointer', border: '1px solid rgba(220,38,38,0.2)', background: 'rgba(220,38,38,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" />
                      </svg>
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </SellerLayout>
  )
}
