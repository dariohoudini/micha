import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const S = { fontFamily: "'DM Sans',sans-serif" }

function ProductCard({ product }) {
  const navigate = useNavigate()
  const discount = product.original_price && product.original_price > product.price
    ? Math.round((1 - product.price / product.original_price) * 100) : null
  return (
    <button onClick={() => navigate(`/product/${product.id}`)}
      style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 150, background: product.image_color || '#1E1E1E', position: 'relative', overflow: 'hidden' }}>
        {product.image_url && <img src={product.image_url} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />}
        {discount && (
          <div style={{ position: 'absolute', top: 8, left: 8, background: '#dc2626', borderRadius: 5, padding: '2px 6px' }}>
            <span style={{ ...S, fontSize: 10, fontWeight: 700, color: '#FFF' }}>-{discount}%</span>
          </div>
        )}
      </div>
      <div style={{ padding: '8px 10px 12px', flex: 1 }}>
        <p style={{ ...S, fontSize: 12, color: '#FFF', fontWeight: 500, marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{product.name}</p>
        <span style={{ ...S, fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{fmt(product.price)}</span>
        {product.avg_rating > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 3, marginTop: 4 }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
            <span style={{ ...S, fontSize: 10, color: '#9A9A9A' }}>{product.avg_rating.toFixed(1)}</span>
          </div>
        )}
      </div>
    </button>
  )
}

function SkeletonCard() {
  return (
    <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
      <div className="skeleton" style={{ height: 150 }} />
      <div style={{ padding: '8px 10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="skeleton" style={{ height: 12, width: '90%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 12, width: '55%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 14, width: '45%', borderRadius: 5, marginTop: 2 }} />
      </div>
    </div>
  )
}

export default function StorePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [store, setStore] = useState(null)
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [productsLoading, setProductsLoading] = useState(true)
  const [sort, setSort] = useState('popular')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  useEffect(() => {
    client.get(`/api/v1/stores/${id}/`)
      .then(r => setStore(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    setProductsLoading(true)
    setPage(1)
    client.get(`/api/v1/products/`, { params: { store: id, ordering: sort === 'popular' ? '-sold_count' : sort === 'price_asc' ? 'price' : sort === 'price_desc' ? '-price' : '-created_at', limit: 20, page: 1 } })
      .then(r => {
        const data = r.data
        setProducts(data.results || data || [])
        setHasMore(!!(data.next))
      })
      .catch(() => setProducts([]))
      .finally(() => setProductsLoading(false))
  }, [id, sort])

  const initials = (store?.name || '?').slice(0, 2).toUpperCase()
  const memberSince = store?.created_at ? new Date(store.created_at).getFullYear() : null

  return (
    <BuyerLayout>
      {/* Header skeleton */}
      {loading && (
        <div style={{ flexShrink: 0 }}>
          <div className="skeleton" style={{ height: 120, width: '100%', borderRadius: 0 }} />
          <div style={{ padding: '0 16px 16px', background: '#0A0A0A', borderBottom: '1px solid #1E1E1E' }}>
            <div className="skeleton" style={{ width: 72, height: 72, borderRadius: '50%', marginTop: -36, marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 18, width: '55%', borderRadius: 8, marginBottom: 8 }} />
            <div className="skeleton" style={{ height: 12, width: '80%', borderRadius: 6 }} />
          </div>
        </div>
      )}

      {/* Store header */}
      {!loading && store && (
        <div style={{ flexShrink: 0 }}>
          {/* Banner */}
          <div style={{ height: 130, background: store.banner_color || 'linear-gradient(135deg,#C9A84C22,#1E1E1E)', position: 'relative', overflow: 'hidden' }}>
            {store.banner_image && <img src={store.banner_image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
            <button onClick={() => navigate(-1)} style={{ position: 'absolute', top: 'max(16px,env(safe-area-inset-top))', left: 16, width: 36, height: 36, borderRadius: 10, background: 'rgba(10,10,10,0.7)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
            </button>
          </div>

          <div style={{ padding: '0 16px 16px', background: '#0A0A0A', borderBottom: '1px solid #1E1E1E' }}>
            {/* Avatar */}
            <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'linear-gradient(135deg,#C9A84C,#A67C35)', border: '3px solid #0A0A0A', marginTop: -36, marginBottom: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0 }}>
              {store.logo
                ? <img src={store.logo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 22, fontWeight: 700, color: '#0A0A0A' }}>{initials}</span>
              }
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <h1 style={{ fontFamily: "'Playfair Display',serif", fontSize: 20, fontWeight: 700, color: '#FFF' }}>{store.name}</h1>
                  {store.is_verified && (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="#C9A84C" aria-label="Loja verificada">
                      <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  )}
                </div>
                {store.tagline && <p style={{ ...S, fontSize: 13, color: '#9A9A9A', marginTop: 3 }}>{store.tagline}</p>}
              </div>
              <button onClick={() => navigate(`/chat`)} style={{ padding: '8px 16px', borderRadius: 12, border: '1px solid #2A2A2A', background: '#141414', ...S, fontSize: 13, fontWeight: 600, color: '#FFF', cursor: 'pointer', flexShrink: 0 }}>
                Mensagem
              </button>
            </div>

            {/* Stats row */}
            <div style={{ display: 'flex', gap: 20, marginTop: 14 }}>
              {[
                { label: 'Produtos', value: store.product_count || 0 },
                { label: 'Vendas', value: store.total_sales || 0 },
                { label: 'Avaliação', value: store.avg_rating > 0 ? `★ ${store.avg_rating.toFixed(1)}` : '—' },
                ...(memberSince ? [{ label: 'Membro desde', value: memberSince }] : []),
              ].map(stat => (
                <div key={stat.label}>
                  <p style={{ ...S, fontSize: 15, fontWeight: 700, color: '#FFF' }}>{stat.value}</p>
                  <p style={{ ...S, fontSize: 10, color: '#9A9A9A', marginTop: 1 }}>{stat.label}</p>
                </div>
              ))}
            </div>

            {store.description && (
              <p style={{ ...S, fontSize: 13, color: '#CCCCCC', marginTop: 12, lineHeight: 1.6 }}>{store.description}</p>
            )}

            {/* Trust badges */}
            <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              {store.is_verified && (
                <span style={{ ...S, fontSize: 11, color: '#059669', background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 6, padding: '3px 8px' }}>✓ Loja verificada</span>
              )}
              {store.avg_response_minutes && store.avg_response_minutes < 60 && (
                <span style={{ ...S, fontSize: 11, color: '#3b82f6', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.2)', borderRadius: 6, padding: '3px 8px' }}>⚡ Resposta rápida</span>
              )}
              {store.return_policy_days > 0 && (
                <span style={{ ...S, fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 6, padding: '3px 8px' }}>↩ {store.return_policy_days} dias devolução</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Sort tabs */}
      <div style={{ display: 'flex', gap: 6, padding: '12px 16px', overflowX: 'auto', scrollbarWidth: 'none', flexShrink: 0, borderBottom: '1px solid #1E1E1E' }}>
        {[
          { v: 'popular',    l: 'Populares' },
          { v: 'new',        l: 'Novos' },
          { v: 'price_asc',  l: 'Preço ↑' },
          { v: 'price_desc', l: 'Preço ↓' },
        ].map(o => (
          <button key={o.v} onClick={() => setSort(o.v)}
            style={{ padding: '6px 14px', borderRadius: 20, flexShrink: 0, border: `1px solid ${sort === o.v ? '#C9A84C' : '#2A2A2A'}`, background: sort === o.v ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: sort === o.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', fontWeight: sort === o.v ? 600 : 400 }}>
            {o.l}
          </button>
        ))}
      </div>

      {/* Products grid */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: 16 }}>
          {productsLoading ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : products.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 0', gap: 12 }}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0" /></svg>
              <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>Esta loja ainda não tem produtos.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {products.map(p => <ProductCard key={p.id} product={p} />)}
            </div>
          )}
          {hasMore && !productsLoading && (
            <button onClick={() => {
              const nextPage = page + 1
              setPage(nextPage)
              client.get(`/api/v1/products/`, { params: { store: id, ordering: sort === 'popular' ? '-sold_count' : sort === 'price_asc' ? 'price' : sort === 'price_desc' ? '-price' : '-created_at', limit: 20, page: nextPage } })
                .then(r => {
                  const data = r.data
                  setProducts(prev => [...prev, ...(data.results || [])])
                  setHasMore(!!data.next)
                }).catch(() => {})
            }} style={{ width: '100%', marginTop: 16, padding: '12px 0', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 14, color: '#9A9A9A', cursor: 'pointer' }}>
              Ver mais produtos
            </button>
          )}
        </div>
      </div>
    </BuyerLayout>
  )
}
