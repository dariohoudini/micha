import { useState, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import ProductCard from '@/components/buyer/ProductCard'
import CategoryPills from '@/components/buyer/CategoryPills'
import FilterDrawer from '@/components/buyer/FilterDrawer'
import { useDebounce } from '@/hooks/useUtils'
import { MOCK_PRODUCTS } from '@/components/buyer/mockData'

const TRENDING_SEARCHES = ['Capulana', 'Samsung', 'Nike', 'Perfume', 'Panelas', 'Ténis']
const RECENT_KEY = 'micha_recent_searches'

function getRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] }
}
function saveRecent(q) {
  const prev = getRecent().filter(s => s !== q)
  localStorage.setItem(RECENT_KEY, JSON.stringify([q, ...prev].slice(0, 6)))
}

export default function ExplorePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [query, setQuery] = useState(location.state?.query || '')
  const [category, setCategory] = useState('all')
  const [sortBy, setSortBy] = useState('popular')
  const [showFilter, setShowFilter] = useState(false)
  const [filters, setFilters] = useState({ priceMin: 0, priceMax: Infinity, minRating: null, expressOnly: false })
  const [recent, setRecent] = useState(getRecent)

  const debouncedQuery = useDebounce(query, 300)

  const filtered = MOCK_PRODUCTS
    .filter(p => {
      const matchCat = category === 'all' || p.category === category
      const matchQuery = !debouncedQuery || p.name.toLowerCase().includes(debouncedQuery.toLowerCase()) || p.seller.toLowerCase().includes(debouncedQuery.toLowerCase())
      const matchPrice = p.price >= filters.priceMin && p.price <= filters.priceMax
      const matchRating = !filters.minRating || p.rating >= filters.minRating
      const matchExpress = !filters.expressOnly || p.express
      return matchCat && matchQuery && matchPrice && matchRating && matchExpress
    })
    .sort((a, b) => {
      if (sortBy === 'price_asc') return a.price - b.price
      if (sortBy === 'price_desc') return b.price - a.price
      if (sortBy === 'rating') return b.rating - a.rating
      return b.sold - a.sold
    })

  const handleSearch = (q) => {
    setQuery(q)
    if (q.trim()) { saveRecent(q.trim()); setRecent(getRecent()) }
  }

  const hasActiveFilters = filters.priceMin > 0 || filters.priceMax < Infinity || filters.minRating || filters.expressOnly
  const showSuggestions = !debouncedQuery

  return (
    <BuyerLayout>
      {/* Search header */}
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '11px 14px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            <input type="text" value={query} onChange={e => handleSearch(e.target.value)}
              placeholder="Pesquisar produtos..." autoFocus
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }} />
            {query && (
              <button onClick={() => setQuery('')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              </button>
            )}
          </div>
          {/* Filter button */}
          <button onClick={() => setShowFilter(true)}
            style={{ width: 44, height: 44, borderRadius: 14, background: hasActiveFilters ? 'rgba(201,168,76,0.1)' : '#1E1E1E', border: `1px solid ${hasActiveFilters ? '#C9A84C' : '#2A2A2A'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0, position: 'relative' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={hasActiveFilters ? '#C9A84C' : '#9A9A9A'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="6" x2="20" y2="6" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="11" y1="18" x2="13" y2="18" />
            </svg>
            {hasActiveFilters && <div style={{ position: 'absolute', top: 6, right: 6, width: 6, height: 6, borderRadius: '50%', background: '#C9A84C' }} />}
          </button>
        </div>

        {/* Categories */}
        <CategoryPills selected={category} onSelect={setCategory} />

        {/* Sort + count */}
        <div style={{ display: 'flex', gap: 8, padding: '10px 0', overflowX: 'auto', scrollbarWidth: 'none', alignItems: 'center' }}>
          {[{ v: 'popular', l: 'Popular' }, { v: 'rating', l: '⭐ Avaliação' }, { v: 'price_asc', l: 'Preço ↑' }, { v: 'price_desc', l: 'Preço ↓' }].map(opt => (
            <button key={opt.v} onClick={() => setSortBy(opt.v)}
              style={{ padding: '6px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${sortBy === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: sortBy === opt.v ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: sortBy === opt.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {opt.l}
            </button>
          ))}
          {debouncedQuery && (
            <span style={{ marginLeft: 'auto', fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', whiteSpace: 'nowrap', paddingRight: 4 }}>
              {filtered.length} resultados
            </span>
          )}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {showSuggestions ? (
          <div style={{ padding: '0 16px 20px' }}>
            {/* Recent searches */}
            {recent.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A' }}>Pesquisas recentes</p>
                  <button onClick={() => { localStorage.removeItem(RECENT_KEY); setRecent([]) }} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>Limpar</button>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {recent.map(s => (
                    <button key={s} onClick={() => handleSearch(s)}
                      style={{ padding: '7px 14px', borderRadius: 50, border: '1px solid #2A2A2A', background: '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 .49-3.96" /></svg>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Trending */}
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12 }}>Pesquisas em alta</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {TRENDING_SEARCHES.map((s, i) => (
                  <button key={s} onClick={() => handleSearch(s)}
                    style={{ padding: '7px 14px', borderRadius: 50, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, color: '#FFFFFF' }}>
                    <span style={{ color: '#C9A84C', fontWeight: 700, fontSize: 11 }}>#{i + 1}</span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div>
            {filtered.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '0 16px 20px' }}>
                {filtered.map(p => <ProductCard key={p.id} product={p} onPress={() => navigate(`/product/${p.id}`)} />)}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 32px', gap: 12 }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>Sem resultados para "{debouncedQuery}"</p>
                <button onClick={() => { setQuery(''); setFilters({ priceMin: 0, priceMax: Infinity, minRating: null, expressOnly: false }) }} className="btn-secondary" style={{ width: 'auto', padding: '10px 24px' }}>Limpar filtros</button>
              </div>
            )}
          </div>
        )}
      </div>

      <FilterDrawer visible={showFilter} onClose={() => setShowFilter(false)} onApply={setFilters} />
    </BuyerLayout>
  )
}
