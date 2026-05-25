/**
 * EmptyCartRecovery — empty cart with recovery CTAs + product
 * recommendations.
 *
 * Why this exists
 * ───────────────
 * The flat "Your cart is empty — browse products" message is the most
 * common bounce-out point for marketplace cart pages. Empathy + a
 * one-tap path to popular products keeps the user in the funnel.
 *
 * What it shows
 * ─────────────
 *   1. Friendly empty-state illustration + copy
 *   2. CTA chips: Categorias Populares · Promoções · Frete Grátis
 *   3. Quick-browse 6-product carousel from the recommendations API
 *      (apps/recommendations backend; falls back to popular products
 *      if the personalisation service is unavailable)
 *
 * On error or empty recommendation response, the CTA chips alone are
 * enough — never blank screen.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'
import { ProductCardSkeleton } from '@/components/ui/Skeleton'


const QUICK_LINKS = [
  { label: 'Categorias', to: '/explore', icon: '🛍️' },
  { label: 'Promoções', to: '/explore?has_discount=1', icon: '🔥' },
  { label: 'Frete Grátis', to: '/explore?free_shipping=1', icon: '🚚' },
]


export default function EmptyCartRecovery() {
  const navigate = useNavigate()
  const [products, setProducts] = useState(null)  // null = loading, [] = empty
  const [error, setError] = useState(false)

  useEffect(() => {
    let aborted = false
    // Try personalised recommendations first; fall back to popular.
    client.get('/api/v1/recommendations/?limit=6')
      .then((r) => {
        if (aborted) return
        const list = r.data?.results || r.data?.products || r.data || []
        if (Array.isArray(list) && list.length > 0) {
          setProducts(list.slice(0, 6))
          return
        }
        throw new Error('empty')
      })
      .catch(() => {
        if (aborted) return
        // Popular fallback.
        client.get('/api/v1/products/?ordering=-views&page_size=6')
          .then((r) => {
            if (aborted) return
            const list = r.data?.results || []
            setProducts(list.slice(0, 6))
          })
          .catch(() => {
            if (aborted) return
            setError(true)
            setProducts([])
          })
      })

    return () => { aborted = true }
  }, [])

  return (
    <div
      role="region"
      aria-label="Carrinho vazio"
      style={{
        display: 'flex', flexDirection: 'column',
        padding: '40px 16px 80px', gap: 24,
      }}
    >
      {/* Empathy header */}
      <div style={{ textAlign: 'center' }}>
        <div aria-hidden="true" style={{ fontSize: 56, marginBottom: 12 }}>🛒</div>
        <h2 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 20, fontWeight: 700, color: '#FFFFFF',
          margin: '0 0 8px',
        }}>
          O teu carrinho está vazio
        </h2>
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 13, color: '#9A9A9A', margin: 0, lineHeight: 1.5,
        }}>
          Descobre produtos de vendedores verificados perto de ti.
        </p>
      </div>

      {/* Quick links */}
      <div
        role="navigation"
        aria-label="Atalhos para explorar"
        style={{
          display: 'flex', gap: 8, justifyContent: 'center',
          flexWrap: 'wrap',
        }}
      >
        {QUICK_LINKS.map(({ label, to, icon }) => (
          <button
            key={to}
            onClick={() => navigate(to)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '10px 16px', borderRadius: 999,
              background: 'rgba(201, 168, 76, 0.1)',
              border: '1px solid rgba(201, 168, 76, 0.3)',
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 13, fontWeight: 600, color: '#C9A84C',
              cursor: 'pointer', minHeight: 40,
            }}
          >
            <span aria-hidden="true">{icon}</span>
            {label}
          </button>
        ))}
      </div>

      {/* Product recs */}
      {(products === null || products.length > 0) && !error && (
        <div>
          <h3 style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 13, fontWeight: 700, color: '#FFFFFF',
            textTransform: 'uppercase', letterSpacing: '0.06em',
            margin: '0 0 12px', textAlign: 'center',
          }}>
            Populares agora
          </h3>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10,
          }}>
            {products === null
              ? Array.from({ length: 4 }).map((_, i) => <ProductCardSkeleton key={i} />)
              : products.map((p) => (
                <button
                  key={p.id}
                  onClick={() => navigate(`/product/${p.id}`)}
                  style={{
                    background: '#1E1E1E', border: '1px solid #2A2A2A',
                    borderRadius: 12, padding: 0, cursor: 'pointer',
                    overflow: 'hidden', textAlign: 'left',
                  }}
                >
                  {(p.image_url || p.images?.[0]?.image) && (
                    <img
                      src={p.image_url || p.images[0].image}
                      alt={p.title || p.name}
                      loading="lazy"
                      style={{
                        width: '100%', aspectRatio: '1', objectFit: 'cover',
                        display: 'block',
                      }}
                    />
                  )}
                  <div style={{ padding: 10 }}>
                    <p style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 12, color: '#FFFFFF', margin: 0,
                      overflow: 'hidden', textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>{p.title || p.name}</p>
                    <p style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 13, fontWeight: 700, color: '#C9A84C',
                      margin: '4px 0 0',
                    }}>
                      {Number(p.price || 0).toLocaleString('pt-AO')} Kz
                    </p>
                  </div>
                </button>
              ))}
          </div>
        </div>
      )}

      {/* Generic explore CTA (always-on safety net) */}
      <button
        onClick={() => navigate('/explore')}
        style={{
          marginTop: 8, padding: '14px 0', borderRadius: 14,
          border: 'none', background: '#C9A84C',
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 14, fontWeight: 700, color: '#0A0A0A',
          cursor: 'pointer', minHeight: 48,
        }}
      >
        Explorar todos os produtos
      </button>
    </div>
  )
}
