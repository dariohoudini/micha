import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BottomNav from '@/components/shared/BottomNav'
import ProductCard from '@/components/buyer/ProductCard'
import CategoryPills from '@/components/buyer/CategoryPills'
import { MOCK_PRODUCTS } from '@/components/buyer/mockData'

export default function ExplorePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [query, setQuery] = useState(location.state?.query || '')
  const [category, setCategory] = useState('all')
  const [sortBy, setSortBy] = useState('popular')

  const filtered = MOCK_PRODUCTS
    .filter(p => {
      const matchCat = category === 'all' || p.category === category
      const matchQuery = !query || p.name.toLowerCase().includes(query.toLowerCase()) || p.seller.toLowerCase().includes(query.toLowerCase())
      const matchExpress = location.state?.filter === 'express' ? p.express : true
      return matchCat && matchQuery && matchExpress
    })
    .sort((a, b) => {
      if (sortBy === 'price_asc') return a.price - b.price
      if (sortBy === 'price_desc') return b.price - a.price
      if (sortBy === 'rating') return b.rating - a.rating
      return b.sold - a.sold // popular
    })

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>

      {/* Search header */}
      <div style={{ padding: '52px 16px 12px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={() => navigate(-1)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
              stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>

          {/* Search input */}
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', gap: 10,
            background: '#1E1E1E', border: '1px solid #2A2A2A',
            borderRadius: 14, padding: '11px 16px',
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Pesquisar produtos..."
              autoFocus
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF',
              }}
            />
            {query && (
              <button onClick={() => setQuery('')}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {/* Categories */}
        <CategoryPills selected={category} onSelect={setCategory} />
      </div>

      {/* Sort bar */}
      <div style={{
        display: 'flex', gap: 8, padding: '8px 16px 12px',
        overflowX: 'auto', scrollbarWidth: 'none', flexShrink: 0,
      }}>
        {[
          { value: 'popular', label: 'Popular' },
          { value: 'rating', label: 'Avaliação' },
          { value: 'price_asc', label: 'Preço ↑' },
          { value: 'price_desc', label: 'Preço ↓' },
        ].map(opt => (
          <button key={opt.value} onClick={() => setSortBy(opt.value)}
            style={{
              padding: '6px 14px', borderRadius: 50, flexShrink: 0,
              border: `1px solid ${sortBy === opt.value ? '#C9A84C' : '#2A2A2A'}`,
              background: sortBy === opt.value ? 'rgba(201,168,76,0.1)' : 'transparent',
              fontFamily: "'DM Sans', sans-serif", fontSize: 12,
              color: sortBy === opt.value ? '#C9A84C' : '#9A9A9A',
              cursor: 'pointer', whiteSpace: 'nowrap',
            }}>
            {opt.label}
          </button>
        ))}
        <span style={{
          marginLeft: 'auto', fontFamily: "'DM Sans', sans-serif",
          fontSize: 12, color: '#9A9A9A', whiteSpace: 'nowrap',
          display: 'flex', alignItems: 'center', paddingRight: 4,
        }}>
          {filtered.length} resultados
        </span>
      </div>

      {/* Results grid */}
      <div className="screen" style={{ flex: 1 }}>
        {filtered.length > 0 ? (
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr',
            gap: 12, padding: '0 16px 20px',
          }}>
            {filtered.map(product => (
              <ProductCard
                key={product.id}
                product={product}
                onPress={() => navigate(`/product/${product.id}`)}
              />
            ))}
          </div>
        ) : (
          <div style={{
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            height: '60%', gap: 16, padding: '0 32px',
          }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
              stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <p style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 14, color: '#9A9A9A', textAlign: 'center',
            }}>
              Sem resultados para "{query}"
            </p>
            <button onClick={() => { setQuery(''); setCategory('all') }}
              className="btn-secondary" style={{ width: 'auto', padding: '10px 24px' }}>
              Limpar filtros
            </button>
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}
