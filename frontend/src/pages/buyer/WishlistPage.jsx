import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { unwatchPrice, trackCartAdd } from '@/api/ai'
import { useCartStore } from '@/stores/cartStore'

export default function WishlistPage() {
  const navigate = useNavigate()
  const addToCart = useCartStore(s => s.addItem)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [priceWatches, setPriceWatches] = useState({})

  useEffect(() => {
    loadWishlist()
    loadPriceWatches()
  }, [])

  const loadWishlist = async () => {
    try {
      const res = await client.get('/api/wishlist/')
      setItems(res.data.results || res.data || [])
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const loadPriceWatches = async () => {
    try {
      const { getPriceWatches } = await import('@/api/ai')
      const res = await getPriceWatches()
      const watches = {}
      ;(res.data || []).forEach(w => { watches[w.product_id] = w })
      setPriceWatches(watches)
    } catch {}
  }

  const removeFromWishlist = async (productId) => {
    try {
      await client.delete(`/api/wishlist/${productId}/`)
      await unwatchPrice(productId)
      setItems(prev => prev.filter(i => (i.product?.id || i.id) !== productId))
    } catch {}
  }

  const handleAddToCart = (product) => {
    addToCart(product)
    trackCartAdd(product)
  }

  return (
    <BuyerLayout>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
            Lista de desejos {items.length > 0 && `(${items.length})`}
          </h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '50%', gap: 16, padding: '0 32px' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>
              A sua lista de desejos está vazia.
            </p>
            <button className="btn-primary" onClick={() => navigate('/explore')} style={{ width: 'auto', padding: '10px 24px' }}>
              Explorar produtos
            </button>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {items.map(item => {
              const product = item.product || item
              const pid = product.id
              const watch = priceWatches[pid]
              const priceDrop = watch && Number(product.price) < Number(watch.price_when_added)
              const dropPct = priceDrop
                ? Math.round(((Number(watch.price_when_added) - Number(product.price)) / Number(watch.price_when_added)) * 100)
                : null

              return (
                <div key={pid} style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 14, display: 'flex', gap: 12 }}>
                  {/* Product image */}
                  <button onClick={() => navigate(`/product/${pid}`)}
                    style={{ width: 80, height: 80, borderRadius: 12, background: '#1E1E1E', flexShrink: 0, overflow: 'hidden', border: 'none', cursor: 'pointer', padding: 0 }}>
                    {product.image_url && <img src={product.image_url} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                  </button>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500, color: '#FFFFFF', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {product.name}
                    </p>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: priceDrop ? '#059669' : '#C9A84C' }}>
                        {Number(product.price).toLocaleString()} Kz
                      </span>
                      {priceDrop && (
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#059669', background: 'rgba(5,150,105,0.1)', padding: '2px 6px', borderRadius: 10 }}>
                          ↓ -{dropPct}%
                        </span>
                      )}
                    </div>

                    {/* Price alert status */}
                    {watch && (
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginBottom: 8 }}>
                        🔔 Alerta de preço activo (queda de {watch.alert_threshold_pct}%)
                      </p>
                    )}

                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => handleAddToCart(product)}
                        style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#0A0A0A', cursor: 'pointer' }}>
                        Adicionar ao carrinho
                      </button>
                      <button onClick={() => removeFromWishlist(pid)}
                        style={{ width: 36, borderRadius: 10, border: '1px solid rgba(220,38,38,0.2)', background: 'rgba(220,38,38,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </BuyerLayout>
  )
}
