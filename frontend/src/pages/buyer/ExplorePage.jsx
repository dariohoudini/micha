// ExplorePage.jsx
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const smartSearch = async (query, filters = {}) => {
  try {
    const res = await client.post('/api/v1/ai/smart-search/', { query, ...filters })
    return res.data.results || res.data || []
  } catch {
    // Fallback to regular search
    const res = await client.get('/api/v1/search/', { params: { q: query, ...filters } })
    return res.data.results || res.data || []
  }
}

export function ExplorePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState(location.state?.query || '')
  const [sort, setSort] = useState('-created_at')
  const [total, setTotal] = useState(0)
  const timeout = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ ordering: sort, limit: 20 })
      if (query.trim()) params.set('search', query.trim())
      const res = await client.get(`/api/v1/products/?${params}`)
      const results = res.data.results || res.data || []
      setProducts(results)
      setTotal(res.data.count || results.length)
    } catch { setProducts([]) }
    finally { setLoading(false) }
  }, [query, sort])

  useEffect(() => {
    clearTimeout(timeout.current)
    timeout.current = setTimeout(load, query ? 400 : 0)
  }, [load])

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <BuyerLayout>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '11px 16px', marginBottom: 12 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Pesquisar produtos..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', ...S, fontSize: 14, color: '#FFFFFF' }} />
          {query && <button onClick={() => setQuery('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9A9A9A', fontSize: 16 }}>✕</button>}
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 10, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {[{v:'-created_at',l:'Recentes'},{v:'price',l:'Preço ↑'},{v:'-price',l:'Preço ↓'},{v:'-avg_rating',l:'Avaliação'}].map(opt => (
            <button key={opt.v} onClick={() => setSort(opt.v)}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${sort === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: sort === opt.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 11, color: sort === opt.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {opt.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 20px' }}>
          {total > 0 && <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 10 }}>{total} resultados</p>}
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
            </div>
          ) : products.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12 }}>
              <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>Sem resultados{query ? ` para "${query}"` : ''}.</p>
              {query && <button onClick={() => setQuery('')} style={{ ...S, fontSize: 13, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>Ver todos os produtos</button>}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {products.map(product => (
                <button key={product.id} onClick={() => navigate(`/product/${product.slug || product.id}`)}
                  style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column' }}>
                  <div style={{ height: 150, background: '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {product.images?.[0]?.image
                      ? <img src={product.images[0].image} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      : <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
                    }
                  </div>
                  <div style={{ padding: '10px 10px 12px' }}>
                    <p style={{ ...S, fontSize: 12, fontWeight: 500, color: '#FFFFFF', marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{product.name}</p>
                    <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{Number(product.price).toLocaleString()} Kz</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </BuyerLayout>
  )
}

export default ExplorePage
