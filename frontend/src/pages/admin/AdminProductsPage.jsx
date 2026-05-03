import { useState, useEffect } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444'
const fmt = (n) => Number(n||0).toLocaleString('pt-AO') + ' Kz'

export default function AdminProductsPage() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  useEffect(() => {
    setLoading(true)
    client.get('/api/v1/admin-api/products/').then(r => setProducts(r.data.results || r.data || [])).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleAction = async (productId, action) => {
    try {
      await client.post(`/api/v1/admin-api/products/${productId}/action/`, { action })
      if (action === 'remove') {
        setProducts(prev => prev.filter(p => p.id !== productId))
      } else {
        setProducts(prev => prev.map(p => p.id === productId ? { ...p, is_active: action === 'activate', is_featured: action === 'feature' ? true : p.is_featured } : p))
      }
      showToast(action === 'remove' ? 'Produto removido' : action === 'feature' ? 'Produto destacado' : 'Produto actualizado')
    } catch { showToast('Erro ao processar', 'error') }
  }

  const setProductOfDay = async (productId) => {
    try {
      await client.post('/api/v1/collections/admin/product-of-day/', { product_id: productId })
      showToast('Produto do dia definido!')
    } catch { showToast('Erro ao definir', 'error') }
  }

  const filtered = products.filter(p => {
    const matchSearch = !search || p.title?.toLowerCase().includes(search.toLowerCase()) || p.store_name?.toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === 'all' || (filter === 'active' && p.is_active) || (filter === 'inactive' && !p.is_active) || (filter === 'featured' && p.is_featured)
    return matchSearch && matchFilter
  })

  return (
    <AdminLayout title="Produtos">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, fontFamily: "'DM Sans'", fontSize: 13 }}>{toast.msg}</div>}

        <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 16px' }}>Gestão de Produtos</h1>

        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto' }}>
          {['all', 'active', 'inactive', 'featured'].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ padding: '7px 12px', borderRadius: 8, border: `1px solid ${filter === f ? G : BORDER}`, background: filter === f ? 'rgba(201,168,76,0.1)' : 'none', color: filter === f ? G : MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}>
              {f === 'all' ? 'Todos' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar produto ou loja..." style={{ width: '100%', padding: '11px 14px', background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, color: TEXT, fontFamily: "'DM Sans'", fontSize: 13, outline: 'none', marginBottom: 12, boxSizing: 'border-box' }} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED }}>A carregar...</p> :
            filtered.map(p => (
              <div key={p.id} style={{ background: CARD, borderRadius: 12, border: `1px solid ${p.is_featured ? 'rgba(201,168,76,0.4)' : BORDER}`, padding: 14 }}>
                <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
                  <div style={{ width: 48, height: 48, borderRadius: 8, background: BORDER, flexShrink: 0, overflow: 'hidden' }}>
                    {p.image_url && <img src={p.image_url} alt={p.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 500, color: TEXT, margin: '0 0 2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</p>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: 0 }}>{p.store_name} · {fmt(p.price)}</p>
                  </div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'flex-start' }}>
                    {p.is_featured && <span style={{ padding: '2px 6px', borderRadius: 4, background: 'rgba(201,168,76,0.15)', color: G, fontFamily: "'DM Sans'", fontSize: 9, fontWeight: 700 }}>★ DESTAQUE</span>}
                    <span style={{ padding: '2px 6px', borderRadius: 4, background: p.is_active ? 'rgba(5,150,105,0.15)' : 'rgba(239,68,68,0.15)', color: p.is_active ? GREEN : RED, fontFamily: "'DM Sans'", fontSize: 9, fontWeight: 700 }}>
                      {p.is_active ? 'ACTIVO' : 'INACTIVO'}
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button onClick={() => handleAction(p.id, p.is_active ? 'deactivate' : 'activate')} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: p.is_active ? RED : GREEN, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                    {p.is_active ? 'Desactivar' : 'Activar'}
                  </button>
                  <button onClick={() => handleAction(p.id, 'feature')} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: G, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                    ★ Destacar
                  </button>
                  <button onClick={() => setProductOfDay(p.id)} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                    🌟 Produto do Dia
                  </button>
                  <button onClick={() => { if (confirm(`Remover "${p.title}"?`)) handleAction(p.id, 'remove') }} style={{ padding: '6px 10px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'none', color: RED, fontFamily: "'DM Sans'", fontSize: 11, cursor: 'pointer' }}>
                    🗑️ Remover
                  </button>
                </div>
              </div>
            ))
          }
        </div>
      </div>
    </AdminLayout>
  )
}
