import { useState, useEffect } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const CARD = '#141414'
const BORDER = '#1E1E1E'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

const fmt = (n) => Number(n || 0).toLocaleString() + ' Kz'

export default function RecentlyViewed({ onPress }) {
  const [products, setProducts] = useState([])

  useEffect(() => {
    // Get from browsing session / recommendations feed with type=recent
    client.get('/api/v1/recommendations/feed/', { params: { type: 'recent', limit: 8 } })
      .then(r => setProducts(r.data.results || r.data?.products || []))
      .catch(() => {
        // Fallback: get from local storage
        try {
          const recent = JSON.parse(localStorage.getItem('micha_recent_views') || '[]')
          setProducts(recent.slice(0, 8))
        } catch {}
      })
  }, [])

  if (products.length === 0) return null

  return (
    <div style={{ padding: '0 16px 20px' }}>
      <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 12px' }}>
        Visto recentemente
      </h3>
      <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 4 }}>
        {products.map(product => (
          <button key={product.id} onClick={() => onPress?.(product)} style={{
            width: 110, flexShrink: 0, background: CARD, borderRadius: 12,
            border: `1px solid ${BORDER}`, overflow: 'hidden', cursor: 'pointer', textAlign: 'left',
          }}>
            <div style={{ height: 90, background: product.image_color || '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {product.image_url
                ? <img src={product.image_url} alt={product.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              }
            </div>
            <div style={{ padding: '7px 9px' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: TEXT, margin: '0 0 3px', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.3 }}>
                {product.title || product.name}
              </p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: GOLD, margin: 0 }}>
                {fmt(product.price)}
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

// Track product view in local storage as backup
export function trackRecentView(product) {
  try {
    const recent = JSON.parse(localStorage.getItem('micha_recent_views') || '[]')
    const filtered = recent.filter(p => p.id !== product.id)
    const updated = [product, ...filtered].slice(0, 20)
    localStorage.setItem('micha_recent_views', JSON.stringify(updated))
  } catch {}
}
