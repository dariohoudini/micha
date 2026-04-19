import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import { useCartStore } from '@/stores/cartStore'
import client from '@/api/client'
import {
  trackProductView, trackDwell, trackWishlistAdd,
  trackCartAdd, getSimilarProducts, getSizeRecommendation,
  watchPrice, getReviewsSummary,
} from '@/api/ai'
import { AIChatButton, TrustScoreBadge } from '@/components/ai/AIComponents'

function StarRating({ rating, count }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ display: 'flex', gap: 2 }}>
        {[1,2,3,4,5].map(i => (
          <svg key={i} width="14" height="14" viewBox="0 0 24 24"
            fill={i <= Math.round(rating) ? '#C9A84C' : 'none'}
            stroke="#C9A84C" strokeWidth="1.5">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          </svg>
        ))}
      </div>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>
        {rating?.toFixed(1)} ({count} avaliações)
      </span>
    </div>
  )
}

export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const addToCart = useCartStore(s => s.addItem)

  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState(0)
  const [selectedSize, setSelectedSize] = useState(null)
  const [selectedColor, setSelectedColor] = useState(null)
  const [quantity, setQuantity] = useState(1)
  const [wishlisted, setWishlisted] = useState(false)
  const [addedToCart, setAddedToCart] = useState(false)
  const [similarProducts, setSimilarProducts] = useState([])
  const [sizeRecommendation, setSizeRecommendation] = useState(null)
  const [reviewSummary, setReviewSummary] = useState(null)
  const [activeTab, setActiveTab] = useState('description')
  const dwellTimer = useRef(null)
  const startTime = useRef(Date.now())

  useEffect(() => {
    loadProduct()
    startTime.current = Date.now()

    // Track dwell time on unmount
    return () => {
      const seconds = Math.floor((Date.now() - startTime.current) / 1000)
      if (seconds > 0) trackDwell({ id }, seconds)
    }
  }, [id])

  const loadProduct = async () => {
    try {
      const res = await client.get(`/api/products/${id}/`)
      const p = res.data
      setProduct(p)
      trackProductView(p)

      // Load AI features in parallel
      loadSimilarProducts(p)
      if (p.category) loadSizeRecommendation(p)
      loadReviewSummary(p)
    } catch (err) {
      console.error('Product load failed:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadSimilarProducts = async (p) => {
    try {
      const res = await getSimilarProducts(id)
      if (res.data.product_ids?.length > 0) {
        const idsParam = res.data.product_ids.join(',')
        const productsRes = await fetch(`/api/products/?ids=${idsParam}`)
        const data = await productsRes.json()
        setSimilarProducts(data.results || data || [])
      }
    } catch {}
  }

  const loadSizeRecommendation = async (p) => {
    try {
      const res = await getSizeRecommendation(id, p.category)
      if (res.data.recommended_size) {
        setSizeRecommendation(res.data)
        setSelectedSize(res.data.recommended_size)
      }
    } catch {}
  }

  const loadReviewSummary = async (p) => {
    try {
      const res = await getReviewsSummary(id)
      if (res.data.summary) setSizeRecommendation(res.data)
      setReviewSummary(res.data)
    } catch {}
  }

  const handleWishlist = async () => {
    setWishlisted(v => !v)
    if (!wishlisted) {
      trackWishlistAdd(product)
      await watchPrice(product)
    }
  }

  const handleAddToCart = () => {
    addToCart({ ...product, quantity, selectedSize, selectedColor })
    trackCartAdd(product)
    setAddedToCart(true)
    setTimeout(() => setAddedToCart(false), 2000)
  }

  const handleBuyNow = () => {
    addToCart({ ...product, quantity, selectedSize, selectedColor })
    navigate('/checkout')
  }

  if (loading) return (
    <BuyerLayout hideNav>
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flex: 1 }}>
        <div style={{ width: 28, height: 28, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </div>
      </div>
    </BuyerLayout>
  )

  if (!product) return (
    <BuyerLayout hideNav>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, gap: 16 }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", color: '#9A9A9A' }}>Produto não encontrado.</p>
        <button className="btn-primary" onClick={() => navigate(-1)} style={{ width: 'auto', padding: '10px 24px' }}>Voltar</button>
      </div>
    </BuyerLayout>
  )

  const images = product.images || [{ url: null }]
  const discount = product.original_price && product.original_price > product.price
    ? Math.round((1 - product.price / product.original_price) * 100)
    : null
  const sizes = product.sizes || product.variants?.sizes || []
  const colors = product.colors || product.variants?.colors || []

  return (
    <BuyerLayout hideNav>
      <div className="screen" style={{ flex: 1 }}>

        {/* Image gallery */}
        <div style={{ position: 'relative' }}>
          {/* Main image */}
          <div style={{ height: 320, background: '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            {images[selectedImage]?.url
              ? <img src={images[selectedImage].url} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                </svg>
            }
            {discount && (
              <div style={{ position: 'absolute', top: 16, left: 16, background: '#dc2626', borderRadius: 8, padding: '4px 10px' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#FFFFFF' }}>-{discount}%</span>
              </div>
            )}

            {/* Back button */}
            <button onClick={() => navigate(-1)} style={{ position: 'absolute', top: 16, left: discount ? 70 : 16, width: 36, height: 36, borderRadius: '50%', background: 'rgba(0,0,0,0.5)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
            </button>

            {/* Wishlist */}
            <button onClick={handleWishlist} style={{ position: 'absolute', top: 16, right: 16, width: 36, height: 36, borderRadius: '50%', background: 'rgba(0,0,0,0.5)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill={wishlisted ? '#C9A84C' : 'none'} stroke={wishlisted ? '#C9A84C' : '#FFFFFF'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </button>
          </div>

          {/* Image thumbnails */}
          {images.length > 1 && (
            <div style={{ display: 'flex', gap: 8, padding: '10px 16px', overflowX: 'auto', scrollbarWidth: 'none' }}>
              {images.map((img, i) => (
                <button key={i} onClick={() => setSelectedImage(i)}
                  style={{ width: 56, height: 56, borderRadius: 8, flexShrink: 0, border: `2px solid ${selectedImage === i ? '#C9A84C' : '#2A2A2A'}`, background: '#1E1E1E', overflow: 'hidden', cursor: 'pointer', padding: 0 }}>
                  {img.url && <img src={img.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Product info */}
        <div style={{ padding: '16px 16px 0' }}>
          {/* Name + price */}
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', marginBottom: 8, lineHeight: 1.3 }}>
            {product.name}
          </h1>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 24, fontWeight: 700, color: '#C9A84C' }}>
              {Number(product.price).toLocaleString()} Kz
            </span>
            {product.original_price && (
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: '#9A9A9A', textDecoration: 'line-through' }}>
                {Number(product.original_price).toLocaleString()} Kz
              </span>
            )}
          </div>

          {/* Rating */}
          {product.avg_rating > 0 && (
            <div style={{ marginBottom: 12 }}>
              <StarRating rating={product.avg_rating} count={product.review_count || 0} />
            </div>
          )}

          {/* Express badge */}
          {product.is_express && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.3)', borderRadius: 8, padding: '6px 12px', marginBottom: 16 }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#C9A84C' }}>Express — Entrega hoje em Luanda</span>
            </div>
          )}

          {/* Seller trust score */}
          {product.seller_id && (
            <div style={{ marginBottom: 16 }}>
              <TrustScoreBadge sellerId={product.seller_id} />
            </div>
          )}

          {/* Size selector */}
          {sizes.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF' }}>Tamanho</p>
                {sizeRecommendation && (
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C' }}>
                    ★ Recomendado para si: {sizeRecommendation.recommended_size}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {sizes.map(size => (
                  <button key={size} onClick={() => setSelectedSize(size)}
                    style={{ width: 44, height: 44, borderRadius: 10, border: `1.5px solid ${selectedSize === size ? '#C9A84C' : '#2A2A2A'}`, background: selectedSize === size ? 'rgba(201,168,76,0.1)' : '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: selectedSize === size ? 600 : 400, color: selectedSize === size ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                    {size}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Color selector */}
          {colors.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 8 }}>Cor</p>
              <div style={{ display: 'flex', gap: 8 }}>
                {colors.map(color => (
                  <button key={color.name || color} onClick={() => setSelectedColor(color.name || color)}
                    style={{ width: 32, height: 32, borderRadius: '50%', border: `2.5px solid ${selectedColor === (color.name || color) ? '#C9A84C' : 'transparent'}`, background: color.hex || '#1E1E1E', cursor: 'pointer', outline: `2px solid ${selectedColor === (color.name || color) ? '#C9A84C' : 'transparent'}`, outlineOffset: 2 }} />
                ))}
              </div>
            </div>
          )}

          {/* Quantity */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF' }}>Quantidade</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: '#1E1E1E', borderRadius: 12, border: '1px solid #2A2A2A', overflow: 'hidden' }}>
              <button onClick={() => setQuantity(q => Math.max(1, q - 1))}
                style={{ width: 36, height: 36, background: 'none', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 18 }}>−</button>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', minWidth: 28, textAlign: 'center' }}>{quantity}</span>
              <button onClick={() => setQuantity(q => Math.min(product.stock || 99, q + 1))}
                style={{ width: 36, height: 36, background: 'none', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 18 }}>+</button>
            </div>
            {product.stock !== undefined && (
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: product.stock <= 5 ? '#f59e0b' : '#9A9A9A' }}>
                {product.stock <= 5 ? `⚠️ Só ${product.stock} em stock` : `${product.stock} disponíveis`}
              </span>
            )}
          </div>

          {/* Tabs — Description / Reviews / Shipping */}
          <div style={{ display: 'flex', borderBottom: '1px solid #1E1E1E', marginBottom: 16 }}>
            {[
              { v: 'description', l: 'Descrição' },
              { v: 'reviews', l: 'Avaliações' },
              { v: 'shipping', l: 'Entrega' },
            ].map(tab => (
              <button key={tab.v} onClick={() => setActiveTab(tab.v)}
                style={{ flex: 1, padding: '10px 0', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: activeTab === tab.v ? 600 : 400, color: activeTab === tab.v ? '#C9A84C' : '#9A9A9A', borderBottom: `2px solid ${activeTab === tab.v ? '#C9A84C' : 'transparent'}`, marginBottom: -1 }}>
                {tab.l}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === 'description' && (
            <div style={{ marginBottom: 24 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.7 }}>
                {product.description || 'Sem descrição disponível.'}
              </p>
              {product.tags?.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
                  {product.tags.map(tag => (
                    <span key={tag} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', background: '#141414', border: '1px solid #2A2A2A', padding: '4px 10px', borderRadius: 20 }}>{tag}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'reviews' && (
            <div style={{ marginBottom: 24 }}>
              {/* AI review summary */}
              {reviewSummary?.summary && (
                <div style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 12, padding: '12px 14px', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#C9A84C', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Resumo IA</span>
                  </div>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', lineHeight: 1.5 }}>{reviewSummary.summary}</p>
                  {reviewSummary.pros?.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      {reviewSummary.pros.map(pro => (
                        <p key={pro} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669' }}>✓ {pro}</p>
                      ))}
                      {reviewSummary.cons?.map(con => (
                        <p key={con} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#f59e0b' }}>△ {con}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {product.avg_rating > 0 ? (
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 48, fontWeight: 700, color: '#C9A84C' }}>{product.avg_rating?.toFixed(1)}</p>
                  <StarRating rating={product.avg_rating} count={product.review_count} />
                </div>
              ) : (
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center', padding: '20px 0' }}>
                  Ainda sem avaliações.
                </p>
              )}
            </div>
          )}

          {activeTab === 'shipping' && (
            <div style={{ marginBottom: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { icon: '⚡', title: 'Express (Luanda)', detail: 'Entrega no mesmo dia', available: product.is_express },
                { icon: '📦', title: 'Entrega standard', detail: '2-5 dias úteis', available: true },
                { icon: '↩️', title: 'Devoluções', detail: product.returns_policy || '15 dias após recepção', available: true },
              ].map(item => item.available && (
                <div key={item.title} style={{ display: 'flex', gap: 12, padding: '12px 14px', background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E' }}>
                  <span style={{ fontSize: 20, flexShrink: 0 }}>{item.icon}</span>
                  <div>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', marginBottom: 2 }}>{item.title}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Similar products */}
          {similarProducts.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>
                Produtos semelhantes
              </h2>
              <div style={{ display: 'flex', gap: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
                {similarProducts.slice(0, 6).map(p => (
                  <button key={p.id} onClick={() => navigate(`/product/${p.id}`)}
                    style={{ width: 130, flexShrink: 0, background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', overflow: 'hidden', cursor: 'pointer', textAlign: 'left', padding: 0 }}>
                    <div style={{ height: 100, background: '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {p.image_url && <img src={p.image_url} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                    </div>
                    <div style={{ padding: '8px 8px 10px' }}>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#FFFFFF', marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</p>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>{Number(p.price).toLocaleString()} Kz</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Bottom padding for sticky buttons */}
          <div style={{ height: 100 }} />
        </div>
      </div>

      {/* Sticky add to cart */}
      <div style={{ padding: '12px 16px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', background: '#0A0A0A', borderTop: '1px solid #1E1E1E', flexShrink: 0, display: 'flex', gap: 10 }}>
        <button onClick={handleAddToCart}
          style={{ flex: 1, padding: '14px 0', borderRadius: 14, border: '1.5px solid #C9A84C', background: addedToCart ? '#C9A84C' : 'rgba(201,168,76,0.1)', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: addedToCart ? '#0A0A0A' : '#C9A84C', cursor: 'pointer', transition: 'all 0.2s' }}>
          {addedToCart ? '✓ Adicionado!' : 'Adicionar ao carrinho'}
        </button>
        <button onClick={handleBuyNow}
          style={{ flex: 1, padding: '14px 0', borderRadius: 14, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          Comprar agora
        </button>
      </div>

      {/* AI Chat floating button */}
      <AIChatButton
        productId={id}
        productName={product?.name}
        language="pt"
      />
    </BuyerLayout>
  )
}
