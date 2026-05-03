import { useState, useEffect } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const CARD = '#141414'
const BORDER = '#1E1E1E'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

const fmt = (n) => Number(n || 0).toLocaleString() + ' Kz'

export default function SimilarProducts({ productId, onPress }) {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!productId) return
    client.get(`/api/v1/ai/similar/${productId}/`)
      .then(r => setProducts(r.data.results || r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [productId])

  if (!loading && products.length === 0) return null

  return (
    <div style={{ padding: '0 16px 24px' }}>
      <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 12px' }}>
        Produtos semelhantes
      </h3>
      <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 4 }}>
        {loading ? (
          [1,2,3].map(i => (
            <div key={i} style={{ width: 130, flexShrink: 0, background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
              <div style={{ height: 100, background: '#1E1E1E', animation: 'pulse 1.5s infinite' }} />
              <div style={{ padding: 8 }}>
                <div style={{ height: 10, background: '#1E1E1E', borderRadius: 4, marginBottom: 6 }} />
                <div style={{ height: 10, background: '#1E1E1E', borderRadius: 4, width: '60%' }} />
              </div>
              <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
            </div>
          ))
        ) : (
          products.slice(0, 8).map(product => (
            <button key={product.id} onClick={() => onPress?.(product)} style={{
              width: 130, flexShrink: 0, background: CARD, borderRadius: 12,
              border: `1px solid ${BORDER}`, overflow: 'hidden', cursor: 'pointer', textAlign: 'left',
            }}>
              <div style={{ height: 100, background: product.image_color || '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                {product.image_url
                  ? <img src={product.image_url} alt={product.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                }
              </div>
              <div style={{ padding: '8px 10px' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: TEXT, margin: '0 0 4px', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.3 }}>
                  {product.title || product.name}
                </p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: GOLD, margin: 0 }}>
                  {fmt(product.price)}
                </p>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}
