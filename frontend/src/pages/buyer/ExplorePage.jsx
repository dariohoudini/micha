import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const S = { fontFamily: "'DM Sans', sans-serif" }

const SORT_OPTS = [
  { v: '-sold_count', l: 'Populares' },
  { v: '-created_at', l: 'Recentes' },
  { v: 'price',       l: 'Preço ↑' },
  { v: '-price',      l: 'Preço ↓' },
  { v: '-avg_rating', l: 'Avaliação' },
]

const CATEGORIES = [
  '🛍️ Todos', '👗 Moda', '📱 Tecnologia', '🏠 Casa', '💄 Beleza',
  '🍎 Alimentação', '⚽ Desporto', '👶 Crianças', '🎨 Arte', '💍 Acessórios',
]

const PROVINCES = ['Todas', 'Luanda', 'Benguela', 'Huambo', 'Huíla', 'Cabinda', 'Namibe', 'Malanje', 'Uíge']

const CONDITIONS = [
  { v: '', l: 'Qualquer' },
  { v: 'new', l: 'Novo' },
  { v: 'used', l: 'Usado' },
  { v: 'refurbished', l: 'Recondicionado' },
]

function ProductCard({ product }) {
  const navigate = useNavigate()
  const discount = product.original_price && product.original_price > product.price
    ? Math.round((1 - product.price / product.original_price) * 100) : null
  const img = product.image_url || product.images?.[0]?.image || product.images?.[0]

  return (
    <button onClick={() => navigate(`/product/${product.id}`)}
      style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 155, background: product.image_color || '#1E1E1E', position: 'relative', overflow: 'hidden' }}>
        {img
          ? <img src={img} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
          : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
            </div>
        }
        {discount > 0 && (
          <div style={{ position: 'absolute', top: 8, left: 8, background: '#dc2626', borderRadius: 6, padding: '2px 7px' }}>
            <span style={{ ...S, fontSize: 10, fontWeight: 700, color: '#FFF' }}>-{discount}%</span>
          </div>
        )}
        {product.is_express && (
          <div style={{ position: 'absolute', top: 8, right: 8, background: '#C9A84C', borderRadius: 6, padding: '2px 6px', display: 'flex', alignItems: 'center', gap: 3 }}>
            <svg width="8" height="8" viewBox="0 0 24 24" fill="#0A0A0A"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
            <span style={{ ...S, fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>Express</span>
          </div>
        )}
      </div>
      <div style={{ padding: '8px 10px 12px', flex: 1 }}>
        <p style={{ ...S, fontSize: 12, color: '#FFF', fontWeight: 500, marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.4 }}>
          {product.name}
        </p>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
          <span style={{ ...S, fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{fmt(product.price)}</span>
          {discount > 0 && product.original_price && (
            <span style={{ ...S, fontSize: 10, color: '#9A9A9A', textDecoration: 'line-through' }}>{fmt(product.original_price)}</span>
          )}
        </div>
        {product.avg_rating > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 3, marginTop: 4 }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
            <span style={{ ...S, fontSize: 10, color: '#9A9A9A' }}>{product.avg_rating.toFixed(1)}</span>
            {product.sold_count > 0 && <span style={{ ...S, fontSize: 10, color: '#555' }}> · {product.sold_count} vendidos</span>}
          </div>
        )}
      </div>
    </button>
  )
}

function SkeletonCard() {
  return (
    <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
      <div className="skeleton" style={{ height: 155 }} />
      <div style={{ padding: '8px 10px 12px', display: 'flex', flexDirection: 'column', gap: 7 }}>
        <div className="skeleton" style={{ height: 12, width: '90%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 12, width: '60%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 14, width: '45%', borderRadius: 5, marginTop: 2 }} />
      </div>
    </div>
  )
}

function FilterSheet({ filters, onChange, onClose }) {
  const [local, setLocal] = useState(filters)
  const set = (k, v) => setLocal(p => ({ ...p, [k]: v }))

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 200, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{ background: '#0F0F0F', borderRadius: '20px 20px 0 0', border: '1px solid #1E1E1E', borderBottom: 'none', padding: '0 0 max(24px,env(safe-area-inset-bottom))', maxHeight: '85vh', overflowY: 'auto' }}>
        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A' }} />
        </div>

        <div style={{ padding: '0 20px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h2 style={{ ...S, fontSize: 16, fontWeight: 700, color: '#FFF' }}>Filtros</h2>
            <button onClick={() => setLocal({ minPrice: '', maxPrice: '', province: 'Todas', condition: '', minRating: 0 })}
              style={{ ...S, fontSize: 13, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>
              Limpar tudo
            </button>
          </div>

          {/* Price range */}
          <div style={{ marginBottom: 24 }}>
            <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Intervalo de preço</p>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <input value={local.minPrice} onChange={e => set('minPrice', e.target.value)} placeholder="Mín. Kz"
                type="number" inputMode="numeric"
                style={{ flex: 1, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', ...S, fontSize: 13, color: '#FFF', outline: 'none' }} />
              <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>—</span>
              <input value={local.maxPrice} onChange={e => set('maxPrice', e.target.value)} placeholder="Máx. Kz"
                type="number" inputMode="numeric"
                style={{ flex: 1, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', ...S, fontSize: 13, color: '#FFF', outline: 'none' }} />
            </div>
          </div>

          {/* Province */}
          <div style={{ marginBottom: 24 }}>
            <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Província</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {PROVINCES.map(p => (
                <button key={p} onClick={() => set('province', p)}
                  style={{ padding: '6px 14px', borderRadius: 20, border: `1px solid ${local.province === p ? '#C9A84C' : '#2A2A2A'}`, background: local.province === p ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: local.province === p ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Condition */}
          <div style={{ marginBottom: 24 }}>
            <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Estado</p>
            <div style={{ display: 'flex', gap: 8 }}>
              {CONDITIONS.map(c => (
                <button key={c.v} onClick={() => set('condition', c.v)}
                  style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: `1px solid ${local.condition === c.v ? '#C9A84C' : '#2A2A2A'}`, background: local.condition === c.v ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: local.condition === c.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                  {c.l}
                </button>
              ))}
            </div>
          </div>

          {/* Min rating */}
          <div style={{ marginBottom: 24 }}>
            <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Avaliação mínima</p>
            <div style={{ display: 'flex', gap: 8 }}>
              {[0, 3, 4, 5].map(r => (
                <button key={r} onClick={() => set('minRating', r)}
                  style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: `1px solid ${local.minRating === r ? '#C9A84C' : '#2A2A2A'}`, background: local.minRating === r ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: local.minRating === r ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                  {r === 0 ? 'Todos' : `${r}★+`}
                </button>
              ))}
            </div>
          </div>

          <button onClick={() => { onChange(local); onClose() }}
            style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            Aplicar filtros
          </button>
        </div>
      </div>
    </div>
  )
}

const DEFAULT_FILTERS = { minPrice: '', maxPrice: '', province: 'Todas', condition: '', minRating: 0 }

export default function ExplorePage() {
  const navigate = useNavigate()
  const location = useLocation()

  const [query, setQuery] = useState(location.state?.query || '')
  const [category, setCategory] = useState(() => {
    const incoming = location.state?.category
    if (!incoming) return '🛍️ Todos'
    return CATEGORIES.find(c => c.toLowerCase().includes(incoming.toLowerCase())) || '🛍️ Todos'
  })
  const [sort, setSort] = useState('-sold_count')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [showFilters, setShowFilters] = useState(false)

  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  const debounce = useRef(null)

  const activeFiltersCount = [
    filters.minPrice || filters.maxPrice,
    filters.province !== 'Todas',
    filters.condition !== '',
    filters.minRating > 0,
  ].filter(Boolean).length

  const buildParams = useCallback((pg = 1) => {
    const params = { ordering: sort, limit: 20, page: pg }
    if (query.trim()) params.search = query.trim()
    if (category !== '🛍️ Todos') params.category = category.replace(/^.+\s/, '')
    if (filters.minPrice) params.min_price = filters.minPrice
    if (filters.maxPrice) params.max_price = filters.maxPrice
    if (filters.province !== 'Todas') params.province = filters.province
    if (filters.condition) params.condition = filters.condition
    if (filters.minRating > 0) params.min_rating = filters.minRating
    return params
  }, [query, category, sort, filters])

  const load = useCallback(async (pg = 1) => {
    if (pg === 1) setLoading(true)
    else setLoadingMore(true)
    try {
      const res = await client.get('/api/v1/products/', { params: buildParams(pg) })
      const results = res.data.results || res.data || []
      if (pg === 1) setProducts(results)
      else setProducts(prev => [...prev, ...results])
      setTotal(res.data.count || results.length)
      setHasMore(!!res.data.next)
      setPage(pg)
    } catch { if (pg === 1) setProducts([]) }
    finally { setLoading(false); setLoadingMore(false) }
  }, [buildParams])

  useEffect(() => {
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => load(1), query ? 350 : 0)
  }, [load])

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target
    if (scrollHeight - scrollTop - clientHeight < 250 && hasMore && !loadingMore) {
      load(page + 1)
    }
  }

  const inputStyle = { flex: 1, background: 'none', border: 'none', outline: 'none', ...S, fontSize: 14, color: '#FFF', minWidth: 0 }

  return (
    <BuyerLayout>
      {/* Search bar */}
      <div style={{ padding: '52px 16px 10px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '11px 14px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Pesquisar produtos, lojas..." style={inputStyle} />
            {query && <button onClick={() => setQuery('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9A9A9A', fontSize: 18, lineHeight: 1, flexShrink: 0 }}>×</button>}
          </div>
          <button onClick={() => setShowFilters(true)}
            style={{ position: 'relative', width: 44, height: 44, borderRadius: 12, background: activeFiltersCount > 0 ? 'rgba(201,168,76,0.1)' : '#1E1E1E', border: `1px solid ${activeFiltersCount > 0 ? '#C9A84C' : '#2A2A2A'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke={activeFiltersCount > 0 ? '#C9A84C' : '#9A9A9A'} strokeWidth="2" strokeLinecap="round"><line x1="4" y1="6" x2="20" y2="6" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="11" y1="18" x2="13" y2="18" /></svg>
            {activeFiltersCount > 0 && (
              <div style={{ position: 'absolute', top: 6, right: 6, width: 14, height: 14, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ ...S, fontSize: 8, fontWeight: 700, color: '#0A0A0A' }}>{activeFiltersCount}</span>
              </div>
            )}
          </button>
        </div>
      </div>

      {/* Category pills */}
      <div style={{ display: 'flex', gap: 8, padding: '0 16px 10px', overflowX: 'auto', scrollbarWidth: 'none', flexShrink: 0 }}>
        {CATEGORIES.map(cat => (
          <button key={cat} onClick={() => setCategory(cat)}
            style={{ padding: '6px 14px', borderRadius: 20, flexShrink: 0, border: `1px solid ${category === cat ? '#C9A84C' : '#2A2A2A'}`, background: category === cat ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: category === cat ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', fontWeight: category === cat ? 600 : 400 }}>
            {cat}
          </button>
        ))}
      </div>

      {/* Sort tabs */}
      <div style={{ display: 'flex', gap: 6, padding: '0 16px 10px', overflowX: 'auto', scrollbarWidth: 'none', flexShrink: 0 }}>
        {SORT_OPTS.map(opt => (
          <button key={opt.v} onClick={() => setSort(opt.v)}
            style={{ padding: '5px 12px', borderRadius: 20, flexShrink: 0, border: `1px solid ${sort === opt.v ? '#6366f1' : '#1E1E1E'}`, background: sort === opt.v ? 'rgba(99,102,241,0.1)' : 'transparent', ...S, fontSize: 11, color: sort === opt.v ? '#818cf8' : '#9A9A9A', cursor: 'pointer', fontWeight: sort === opt.v ? 600 : 400 }}>
            {opt.l}
          </button>
        ))}
      </div>

      {/* Results count + active filter chips */}
      {(total > 0 || activeFiltersCount > 0) && (
        <div style={{ padding: '0 16px 8px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
          {total > 0 && <span style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{total.toLocaleString()} resultado{total !== 1 ? 's' : ''}</span>}
          {activeFiltersCount > 0 && (
            <button onClick={() => setFilters(DEFAULT_FILTERS)}
              style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 20, border: '1px solid rgba(220,38,38,0.3)', background: 'rgba(220,38,38,0.08)', ...S, fontSize: 11, color: '#ef4444', cursor: 'pointer' }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              Limpar filtros ({activeFiltersCount})
            </button>
          )}
        </div>
      )}

      {/* Products grid */}
      <div className="screen" style={{ flex: 1 }} onScroll={handleScroll}>
        <div style={{ padding: '0 16px 80px' }}>
          {loading ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {Array.from({ length: 10 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : products.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 32px', gap: 14, textAlign: 'center' }}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
              <p style={{ ...S, fontSize: 15, color: '#9A9A9A' }}>
                Sem resultados{query ? ` para "${query}"` : ''}
              </p>
              {(query || activeFiltersCount > 0) && (
                <button onClick={() => { setQuery(''); setFilters(DEFAULT_FILTERS); setCategory('🛍️ Todos') }}
                  style={{ padding: '10px 24px', borderRadius: 12, border: '1px solid #2A2A2A', background: '#141414', ...S, fontSize: 13, color: '#C9A84C', cursor: 'pointer' }}>
                  Limpar pesquisa
                </button>
              )}
            </div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {products.map(p => <ProductCard key={p.id} product={p} />)}
              </div>
              {loadingMore && (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '20px 0' }}>
                  <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
                </div>
              )}
              {!hasMore && products.length > 0 && (
                <p style={{ ...S, fontSize: 12, color: '#555', textAlign: 'center', padding: '20px 0' }}>Fim dos resultados</p>
              )}
            </>
          )}
        </div>
      </div>

      {showFilters && <FilterSheet filters={filters} onChange={setFilters} onClose={() => setShowFilters(false)} />}
    </BuyerLayout>
  )
}
