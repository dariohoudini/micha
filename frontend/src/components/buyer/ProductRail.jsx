import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const S = { fontFamily: "'DM Sans', sans-serif" }

function MiniCard({ product }) {
  const navigate = useNavigate()
  const img = product.thumbnail || product.image_url || product.images?.[0]?.image
  const discount = product.compare_at_price && product.compare_at_price > product.price
    ? Math.round((1 - product.price / product.compare_at_price) * 100) : null

  return (
    <button onClick={() => navigate(`/product/${product.id}`)}
      style={{
        width: 140, flexShrink: 0, background: '#141414', borderRadius: 14,
        border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left',
        cursor: 'pointer', display: 'flex', flexDirection: 'column', padding: 0,
      }}>
      <div style={{ height: 130, background: '#1E1E1E', position: 'relative', overflow: 'hidden' }}>
        {img
          ? <img src={img} alt={product.title || product.name} loading="lazy"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
            </div>}
        {discount > 0 && (
          <div style={{ position: 'absolute', top: 6, left: 6, background: '#dc2626', borderRadius: 5, padding: '2px 5px' }}>
            <span style={{ ...S, fontSize: 9, fontWeight: 700, color: '#FFF' }}>-{discount}%</span>
          </div>
        )}
      </div>
      <div style={{ padding: '8px 10px 10px', flex: 1 }}>
        <p style={{ ...S, fontSize: 12, color: '#FFF', fontWeight: 500, marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.4 }}>
          {product.title || product.name}
        </p>
        <span style={{ ...S, fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>
          {fmt(product.price)}
        </span>
      </div>
    </button>
  )
}

function SkeletonCard() {
  return (
    <div style={{ width: 140, flexShrink: 0, background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
      <div className="skeleton" style={{ height: 130 }} />
      <div style={{ padding: '8px 10px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="skeleton" style={{ height: 11, width: '90%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 11, width: '60%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 13, width: '50%', borderRadius: 5, marginTop: 2 }} />
      </div>
    </div>
  )
}

/**
 * Generic horizontal product rail.
 *
 * Props:
 *   title          - rail heading (e.g. "Comprados juntos")
 *   icon           - optional emoji prefix (e.g. "🛒")
 *   endpoint       - API path returning { results: [products] }
 *   params         - query params object
 *   minItems       - hide rail if fewer than this many results (default 2)
 *   skeletonCount  - skeletons during initial load
 */
export default function ProductRail({ title, icon, endpoint, params = {}, minItems = 2, skeletonCount = 4 }) {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!endpoint) return
    let cancelled = false
    setLoading(true)
    setError(false)
    client.get(endpoint, { params })
      .then(r => {
        if (cancelled) return
        const data = r.data?.results ?? r.data ?? []
        setProducts(Array.isArray(data) ? data : [])
      })
      .catch(() => { if (!cancelled) setError(true) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line
  }, [endpoint, JSON.stringify(params)])

  if (error) return null
  if (!loading && products.length < minItems) return null

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ padding: '0 16px', marginBottom: 12 }}>
        <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 17, fontWeight: 700, color: '#FFF', margin: 0 }}>
          {icon && <span style={{ marginRight: 6 }}>{icon}</span>}
          {title}
        </h2>
      </div>
      <div style={{ display: 'flex', gap: 10, overflowX: 'auto', padding: '0 16px', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
        {loading
          ? Array.from({ length: skeletonCount }).map((_, i) => <SkeletonCard key={i} />)
          : products.map(p => <MiniCard key={p.id} product={p} />)}
      </div>
    </div>
  )
}
