import { useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { asList } from '@/lib/asList'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'

function useRecommendations(type, params = {}) {
  return useQuery({
    queryKey: ['recommendations', type, params],
    queryFn: async () => {
      const res = await client.get('/api/v1/recommendations/feed/', { params: { type, limit: 10, ...params } })
      return asList(res.data)
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })
}

function ProductCard({ product, onPress }) {
  const navigate = useNavigate()
  const discount = product.original_price && product.original_price > product.price
    ? Math.round((1 - product.price / product.original_price) * 100) : null

  return (
    <button
      onClick={() => { onPress?.(); navigate(`/product/${product.id}`) }}
      style={{
        width: 140, flexShrink: 0,
        background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E',
        overflow: 'hidden', textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column',
        transition: 'border-color 0.2s',
      }}
    >
      <div style={{ height: 130, background: product.image_color || '#1E1E1E', position: 'relative', overflow: 'hidden' }}>
        {product.image_url
          ? <img src={product.image_url} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
          : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
            </div>
        }
        {discount && (
          <div style={{ position: 'absolute', top: 6, left: 6, background: '#dc2626', borderRadius: 5, padding: '2px 5px' }}>
            <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 9, fontWeight: 700, color: '#FFF' }}>-{discount}%</span>
          </div>
        )}
        {product.is_express && (
          <div style={{ position: 'absolute', top: 6, right: 6, background: '#C9A84C', borderRadius: 5, padding: '2px 5px' }}>
            <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>Express</span>
          </div>
        )}
      </div>
      <div style={{ padding: '8px 10px 10px', flex: 1 }}>
        <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 12, color: '#FFF', fontWeight: 500, marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.4 }}>
          {product.name}
        </p>
        <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>
          {fmt(product.price)}
        </span>
        {product.avg_rating > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 3, marginTop: 4 }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
            <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 10, color: '#9A9A9A' }}>{product.avg_rating.toFixed(1)}</span>
          </div>
        )}
      </div>
    </button>
  )
}

function SkeletonCard() {
  return (
    <div style={{ width: 140, flexShrink: 0, background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
      <div className="skeleton" style={{ height: 130, width: '100%' }} />
      <div style={{ padding: '8px 10px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="skeleton" style={{ height: 11, width: '90%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 11, width: '60%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 13, width: '50%', borderRadius: 5, marginTop: 2 }} />
      </div>
    </div>
  )
}

export default function RecommendationCarousel({ title, type, productId, limit = 10 }) {
  const scrollRef = useRef(null)
  const params = productId ? { product_id: productId, limit } : { limit }
  const { data: products = [], isLoading } = useRecommendations(type, params)

  if (!isLoading && products.length === 0) return null

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', marginBottom: 12 }}>
        <h2 style={{ fontFamily: "'Playfair Display',serif", fontSize: 17, fontWeight: 700, color: '#FFF' }}>{title}</h2>
        <button style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 12, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>Ver tudo</button>
      </div>
      <div
        ref={scrollRef}
        style={{ display: 'flex', gap: 10, overflowX: 'auto', padding: '0 16px', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}
      >
        {isLoading
          ? Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)
          : products.map(p => <ProductCard key={p.id} product={p} />)
        }
      </div>
    </div>
  )
}
