import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import { useAuthStore } from '@/stores/authStore'
import {
  getPersonalisedFeed,
  smartSearch,
  trackEvent,
  trackRecommendationClick,
} from '@/api/ai'

// Skeleton loader for product cards
function ProductSkeleton() {
  return (
    <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
      <div style={{ height: 160, background: '#1E1E1E', animation: 'pulse 1.5s ease-in-out infinite' }} />
      <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ height: 12, background: '#1E1E1E', borderRadius: 6, width: '80%', animation: 'pulse 1.5s ease-in-out infinite' }} />
        <div style={{ height: 12, background: '#1E1E1E', borderRadius: 6, width: '50%', animation: 'pulse 1.5s ease-in-out infinite' }} />
      </div>
      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </div>
  )
}

// Product card
function ProductCard({ product, onPress, source = 'home_feed' }) {
  const discount = product.original_price && product.original_price > product.price
    ? Math.round((1 - product.price / product.original_price) * 100)
    : null

  const handlePress = () => {
    trackRecommendationClick(product.id, source)
    onPress(product)
  }

  return (
    <button onClick={handlePress}
      style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column' }}>
      {/* Image */}
      <div style={{ height: 160, background: product.image_color || '#1E1E1E', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%' }}>
        {product.image_url
          ? <img src={product.image_url} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
            </svg>
        }
        {discount && (
          <div style={{ position: 'absolute', top: 8, left: 8, background: '#dc2626', borderRadius: 6, padding: '2px 6px' }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 700, color: '#FFFFFF' }}>-{discount}%</span>
          </div>
        )}
        {product.is_express && (
          <div style={{ position: 'absolute', top: 8, right: 8, background: '#C9A84C', borderRadius: 6, padding: '2px 6px', display: 'flex', alignItems: 'center', gap: 3 }}>
            <svg width="8" height="8" viewBox="0 0 24 24" fill="#0A0A0A"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>Express</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ padding: '10px 10px 12px', flex: 1 }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF', fontWeight: 500, marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {product.name}
        </p>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>
            {Number(product.price).toLocaleString()} Kz
          </span>
          {product.original_price && (
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A', textDecoration: 'line-through' }}>
              {Number(product.original_price).toLocaleString()} Kz
            </span>
          )}
        </div>
        {product.avg_rating > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
            </svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>{product.avg_rating.toFixed(1)}</span>
          </div>
        )}
      </div>
    </button>
  )
}

// Onboarding quiz banner (shown when quiz not completed)
function QuizBanner({ onStart }) {
  return (
    <div style={{ margin: '0 16px', background: 'linear-gradient(135deg, rgba(201,168,76,0.15), rgba(201,168,76,0.05))', borderRadius: 16, border: '1px solid rgba(201,168,76,0.3)', padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(201,168,76,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          </svg>
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C', marginBottom: 2 }}>Personaliza a sua experiência</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>Responda a 5 perguntas rápidas para ver produtos à sua medida</p>
        </div>
      </div>
      <button onClick={onStart} className="btn-primary" style={{ marginTop: 12, padding: '10px 0' }}>
        Começar agora — 1 minuto
      </button>
    </div>
  )
}

// AI personalisation indicator
function PersonalisationBadge({ algorithm, confidence }) {
  if (!algorithm || algorithm === 'cold_start') return null
  const labels = {
    quiz_seeded: 'Baseado nas suas preferências',
    hybrid: 'Personalizado para si',
    behavioral: 'Totalmente personalizado',
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 16px' }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C' }}>
        {labels[algorithm] || 'Produtos recomendados'}
      </span>
    </div>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [algorithm, setAlgorithm] = useState(null)
  const [quizCompleted, setQuizCompleted] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const searchTimeout = useRef(null)
  const LIMIT = 20

  // Load personalised feed
  const loadFeed = useCallback(async (reset = false) => {
    try {
      const currentOffset = reset ? 0 : offset
      if (reset) setLoading(true)
      else setLoadingMore(true)

      const res = await getPersonalisedFeed({ limit: LIMIT, offset: currentOffset })
      const data = res.data

      // Feed returns product IDs — we need to fetch full product data
      if (data.product_ids?.length > 0) {
        const fullProducts = await fetchProductsByIds(data.product_ids, data.scores)
        if (reset) {
          setProducts(fullProducts)
        } else {
          setProducts(prev => [...prev, ...fullProducts])
        }
        setHasMore(data.product_ids.length === LIMIT)
        setOffset(currentOffset + LIMIT)
      } else {
        // No AI products — fall back to trending
        const trending = await fetchTrendingProducts()
        setProducts(trending)
        setHasMore(false)
      }

      setAlgorithm(data.algorithm)
      setQuizCompleted(data.profile?.quiz_completed ?? true)

    } catch (err) {
      console.error('Feed load failed:', err)
      // Graceful fallback to trending
      try {
        const trending = await fetchTrendingProducts()
        setProducts(trending)
      } catch {}
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [offset])

  // Fetch full product data by IDs (AI feed returns IDs only)
  const fetchProductsByIds = async (ids, scores) => {
    try {
      // Call your products API with the IDs
      const idsParam = ids.join(',')
      const res = await fetch(`/api/products/?ids=${idsParam}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('micha_access')}` }
      })
      const data = await res.json()
      const products = data.results || data

      // Attach AI scores for display
      return products.map((p, i) => ({ ...p, ai_score: scores?.[i] }))
    } catch {
      return []
    }
  }

  // Fallback to trending products
  const fetchTrendingProducts = async () => {
    try {
      const res = await fetch('/api/products/?ordering=-created_at&limit=20')
      const data = await res.json()
      return data.results || data
    } catch {
      return []
    }
  }

  // Smart search with debounce
  const handleSearchChange = (value) => {
    setSearchQuery(value)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)

    if (!value.trim()) {
      setSearchResults(null)
      return
    }

    if (value.length < 2) return

    searchTimeout.current = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await smartSearch(value)
        setSearchResults(res.data)
      } catch (err) {
        console.error('Search failed:', err)
      } finally {
        setSearching(false)
      }
    }, 400) // 400ms debounce
  }

  const handleSearchSubmit = () => {
    if (searchQuery.trim()) {
      navigate('/explore', { state: { query: searchQuery, aiResults: searchResults } })
    }
  }

  useEffect(() => {
    loadFeed(true)
    trackEvent('view', { source: 'home_feed' })
  }, [])

  const firstName = user?.username || user?.email?.split('@')[0] || 'Cliente'

  return (
    <BuyerLayout>
      {/* Top bar */}
      <div style={{ padding: '52px 16px 12px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 2 }}>
              Olá, {firstName} 👋
            </p>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
              O que procura hoje?
            </h1>
          </div>
          <button onClick={() => navigate('/notifications')}
            style={{ width: 42, height: 42, borderRadius: 12, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', position: 'relative' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </button>
        </div>

        {/* Smart search bar */}
        <div style={{ position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '11px 16px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={e => handleSearchChange(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearchSubmit()}
              placeholder="Ex: vestido para casamento barato..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }}
            />
            {searching && (
              <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
                <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
              </div>
            )}
          </div>

          {/* AI search suggestions dropdown */}
          {searchResults && searchQuery && (
            <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 14, marginTop: 4, zIndex: 50, overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
              {/* Parsed intent hint */}
              {(searchResults.query?.parsed_category || searchResults.query?.parsed_price_max) && (
                <div style={{ padding: '10px 16px', borderBottom: '1px solid #1E1E1E', background: 'rgba(201,168,76,0.05)' }}>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {searchResults.query?.parsed_category && (
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', padding: '2px 8px', borderRadius: 20 }}>
                        📂 {searchResults.query.parsed_category}
                      </span>
                    )}
                    {searchResults.query?.parsed_price_max && (
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', padding: '2px 8px', borderRadius: 20 }}>
                        💰 Até {Number(searchResults.query.parsed_price_max).toLocaleString()} Kz
                      </span>
                    )}
                    {searchResults.query?.parsed_occasion && (
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', padding: '2px 8px', borderRadius: 20 }}>
                        🎯 {searchResults.query.parsed_occasion}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Quick results */}
              {searchResults.products?.slice(0, 4).map(product => (
                <button key={product.id}
                  onClick={() => { navigate(`/product/${product.id}`); setSearchResults(null) }}
                  style={{ width: '100%', display: 'flex', gap: 12, padding: '10px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid #1E1E1E' }}>
                  <div style={{ width: 36, height: 36, borderRadius: 8, background: '#1E1E1E', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C' }}>{Number(product.price).toLocaleString()} Kz</p>
                  </div>
                </button>
              ))}

              {/* See all results */}
              <button onClick={handleSearchSubmit}
                style={{ width: '100%', padding: '12px 16px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', textAlign: 'center', borderTop: '1px solid #1E1E1E' }}>
                Ver todos os resultados ({searchResults.total || 0}) →
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Quiz banner */}
      {!quizCompleted && (
        <div style={{ marginBottom: 16 }}>
          <QuizBanner onStart={() => navigate('/onboarding/quiz')} />
        </div>
      )}

      {/* Personalisation indicator */}
      {algorithm && algorithm !== 'cold_start' && (
        <div style={{ marginBottom: 8 }}>
          <PersonalisationBadge algorithm={algorithm} />
        </div>
      )}

      {/* Feed */}
      <div className="screen" style={{ flex: 1 }}
        onScroll={e => {
          const { scrollTop, scrollHeight, clientHeight } = e.target
          if (scrollHeight - scrollTop - clientHeight < 200 && hasMore && !loadingMore) {
            loadFeed(false)
          }
        }}>
        <div style={{ paddingBottom: 20 }}>
          {loading ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '0 16px' }}>
              {Array(8).fill(0).map((_, i) => <ProductSkeleton key={i} />)}
            </div>
          ) : products.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 16, padding: '0 32px' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>
                Sem produtos disponíveis. Volte em breve!
              </p>
            </div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '0 16px' }}>
                {products.map(product => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    source={algorithm || 'trending'}
                    onPress={p => navigate(`/product/${p.id}`)}
                  />
                ))}
              </div>

              {/* Load more indicator */}
              {loadingMore && (
                <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}>
                  <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                </div>
              )}

              {!hasMore && products.length > 0 && (
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', textAlign: 'center', padding: '20px 0' }}>
                  Viu todos os produtos recomendados
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </BuyerLayout>
  )
}
