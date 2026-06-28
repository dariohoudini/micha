import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'
import HelperBot from '@/components/shared/HelperBot'
import { SellerOfflineToggle, FlashSaleCreator, ProductBoostUI } from '@/components/shared/MichaUXComponents'
import { haptic } from '@/hooks/useUX'


const formatPrice = (n) => Number(n || 0).toLocaleString() + ' Kz'

export default function SellerProductsPage() {
  const navigate = useNavigate()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 2500) }

  const loadProducts = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (filter === 'active') params.set('is_active', 'true')
      if (filter === 'inactive') params.set('is_active', 'false')
      const res = await client.get(`/api/v1/products/my/?${params}`)
      const all = res.data.results || res.data || []
      setProducts(filter === 'out_of_stock' ? all.filter(p => (p.stock || 0) === 0) : all)
    } catch { setProducts([]) }
    finally { setLoading(false) }
  }, [search, filter])

  useEffect(() => {
    const t = setTimeout(loadProducts, search ? 400 : 0)
    return () => clearTimeout(t)
  }, [loadProducts])

  const toggleActive = async (product) => {
    try {
      await client.patch(`/api/v1/products/${product.id}/update/`, { is_active: !product.is_active })
      setProducts(prev => prev.map(p => p.id === product.id ? { ...p, is_active: !p.is_active } : p))
      showToast(product.is_active ? 'Produto desactivado.' : 'Produto activado.')
    } catch { showToast('Erro ao actualizar.', 'error') }
  }

  const duplicate = async (id) => {
    try {
      await client.post(`/api/v1/products/${id}/duplicate/`)
      showToast('Produto duplicado.')
      loadProducts()
    } catch { showToast('Erro ao duplicar.', 'error') }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <SellerLayout title="Os Meus Produtos">
      {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#fff', padding: '10px 20px', borderRadius: 12, ...S, fontSize: 13, whiteSpace: 'nowrap' }}>{toast.msg}</div>}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '10px 14px', marginBottom: 10 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar produtos..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', ...S, fontSize: 13, color: '#FFFFFF' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {[{v:'all',l:'Todos'},{v:'active',l:'Activos'},{v:'inactive',l:'Inactivos'},{v:'out_of_stock',l:'Esgotados'}].map(f => (
            <button key={f.v} onClick={() => setFilter(f.v)}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#C9A84C' : '#2A2A2A'}`, background: filter === f.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 11, color: filter === f.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
          </div>
        ) : products.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 16 }}>
            <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>Sem produtos encontrados.</p>
            <button onClick={() => navigate('/seller/products/new')} style={{ padding: '10px 24px', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>Adicionar produto</button>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {products.map(product => (
              <div key={product.id} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
                <div style={{ display: 'flex', gap: 12 }}>
                  <div style={{ width: 60, height: 60, borderRadius: 10, background: '#1E1E1E', flexShrink: 0, overflow: 'hidden' }}>
                    {product.images?.[0]?.image && <img src={product.images[0].image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ ...S, fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}</p>
                    <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#C9A84C', marginBottom: 4 }}>{formatPrice(product.price)}</p>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                      <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>Stock: {product.quantity ?? product.stock ?? '—'}</span>
                      {/* AliExpress §17.2 moderation status badge */}
                      {(() => {
                        const ms = product.moderation_status
                        const cfg = ms === 'published' || (!ms && product.is_active)
                          ? { l: 'Publicado', c: '#10b981', bg: 'rgba(16,185,129,0.12)' }
                          : ms === 'under_review'
                            ? { l: 'Em revisão', c: '#f59e0b', bg: 'rgba(245,158,11,0.12)' }
                          : ms === 'violation'
                            ? { l: 'Violação',   c: '#ef4444', bg: 'rgba(239,68,68,0.12)' }
                          : ms === 'sold_out' || (product.quantity === 0)
                            ? { l: 'Esgotado',   c: '#9A9A9A', bg: 'rgba(154,154,154,0.12)' }
                          : ms === 'deactivated' || !product.is_active
                            ? { l: 'Desactivado',c: '#9A9A9A', bg: 'rgba(154,154,154,0.12)' }
                          : { l: 'Activo',      c: '#10b981', bg: 'rgba(16,185,129,0.12)' }
                        return (
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            padding: '2px 8px', borderRadius: 10, background: cfg.bg, color: cfg.c,
                            ...S, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                          }}>
                            <span style={{ width: 4, height: 4, borderRadius: '50%', background: cfg.c }} />
                            {cfg.l}
                          </span>
                        )
                      })()}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <button onClick={() => navigate(`/seller/products/${product.id}/edit`)}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 12, color: '#FFFFFF', cursor: 'pointer' }}>Editar</button>
                  <button onClick={() => toggleActive(product)}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: `1px solid ${product.is_active ? 'rgba(220,38,38,0.3)' : 'rgba(5,150,105,0.3)'}`, background: 'transparent', ...S, fontSize: 12, color: product.is_active ? '#dc2626' : '#059669', cursor: 'pointer' }}>
                    {product.is_active ? 'Desactivar' : 'Activar'}
                  </button>
                  <button onClick={() => duplicate(product.id)}
                    style={{ width: 38, borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <button onClick={() => navigate('/seller/products/new')}
        style={{ position: 'fixed', bottom: 90, right: 16, width: 52, height: 52, borderRadius: '50%', background: '#C9A84C', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 16px rgba(201,168,76,0.4)', zIndex: 40 }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
      </button>
    
      <HelperBot screen="products" isSeller={true} />
      </SellerLayout>
  )
}
