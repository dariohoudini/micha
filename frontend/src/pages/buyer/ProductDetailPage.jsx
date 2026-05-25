import { useProductTracking, trackHighValueEvent } from '@/hooks/useIntentDetector'
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
import HelperBot from '@/components/shared/HelperBot'
import trackInteraction, { INTERACTION_TYPES } from '@/api/tracking'
import PersonalisedPriceBadge from '@/components/buyer/PersonalisedPriceBadge'
import { ReportButton, BlockUserButton } from '@/components/shared/UserActions'
import ReviewsSection from '@/components/buyer/ReviewsSection'
import RecommendationCarousel from '@/components/buyer/RecommendationCarousel'
import ProductRail from '@/components/buyer/ProductRail'
import OtherOffersRail from '@/components/buyer/OtherOffersRail'
import VariantPicker, { findMatchingCombo } from '@/components/buyer/VariantPicker'
import BuyerTrustBanner from '@/components/buyer/BuyerTrustBanner'
import SellerMiniCard from '@/components/buyer/SellerMiniCard'
import BrandProtectedBadge from '@/components/buyer/BrandProtectedBadge'

// Live flash sale lookup for this product
function useFlashSaleForProduct(productId) {
  const [sale, setSale] = useState(null)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!productId) return
    let cancelled = false
    client.get('/api/v1/promotions/flash-sales/')
      .then(r => {
        if (cancelled) return
        const list = r.data.results || r.data || []
        const match = list.find(s => String(s.product_id) === String(productId))
        if (match) setSale(match)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [productId])
  useEffect(() => {
    if (!sale) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [sale])
  if (!sale) return null
  const endMs = new Date(sale.end_time).getTime()
  const remaining = endMs - now
  if (remaining <= 0) return null
  return { sale, remaining }
}

function FlashSaleBadge({ flash }) {
  if (!flash) return null
  const totalSec = Math.floor(flash.remaining / 1000)
  const hours = Math.floor(totalSec / 3600)
  const minutes = Math.floor((totalSec % 3600) / 60)
  const seconds = totalSec % 60
  const pad = (n) => String(n).padStart(2, '0')
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 10, padding: '10px 14px', borderRadius: 12,
      background: 'linear-gradient(135deg, #dc2626 0%, #991b1b 100%)',
      marginBottom: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 16 }}>⚡</span>
        <div>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#FFF', margin: 0 }}>
            Venda Flash · −{Math.round(flash.sale.discount_percentage || 0)}%
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: 'rgba(255,255,255,0.8)', margin: 0 }}>
            Termina em {pad(hours)}:{pad(minutes)}:{pad(seconds)}
          </p>
        </div>
      </div>
    </div>
  )
}

// Live social-proof signals (viewing now / sold recently / in carts / low stock)
function useSocialProof(productId) {
  const [proof, setProof] = useState(null)
  useEffect(() => {
    if (!productId) return
    let cancelled = false
    const url = `/api/v1/recommendations/viewing/${productId}/`
    const tick = () => {
      // Heartbeat first so we count ourselves; ignore errors silently
      client.post(url).catch(() => {})
      client.get(url)
        .then(r => { if (!cancelled) setProof(r.data) })
        .catch(() => {})
    }
    tick()
    const id = setInterval(tick, 30000) // refresh every 30s
    return () => { cancelled = true; clearInterval(id) }
  }, [productId])
  return proof
}

function SocialProofStrip({ proof }) {
  if (!proof) return null
  const items = []
  if (proof.viewing_now > 1) {
    items.push({ icon: '👀', text: `${proof.viewing_now} a ver agora`, color: '#C9A84C' })
  }
  if (proof.sold_recent > 0) {
    items.push({ icon: '🔥', text: `${proof.sold_recent} vendidos nos últimos ${proof.sold_recent_days || 7} dias`, color: '#F97316' })
  }
  if (proof.in_carts > 1) {
    items.push({ icon: '🛒', text: `${proof.in_carts} no carrinho`, color: '#9A9A9A' })
  }
  if (proof.low_stock != null && proof.low_stock <= 10) {
    items.push({ icon: '⚡', text: `Restam apenas ${proof.low_stock}`, color: '#dc2626' })
  }
  if (!items.length) return null

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
      {items.map((it, i) => (
        <span key={i} style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          padding: '5px 10px', borderRadius: 20,
          background: 'rgba(255,255,255,0.04)', border: `1px solid ${it.color}33`,
          fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: it.color,
        }}>
          <span>{it.icon}</span>{it.text}
        </span>
      ))}
    </div>
  )
}
import StickyAddToCart from '@/components/buyer/StickyAddToCart'
import { CartFlyParticle, useCartFly } from '@/components/shared/CartFlyAnimation'
import { haptic } from '@/hooks/useUX'
import { WhatsAppShareButton, PriceDropAlertToggle, ProductQASection } from '@/components/shared/MichaUXComponents'


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


function usePriceHistory(productId) {
  const [history, setHistory] = useState([])
  useEffect(() => {
    if (!productId) return
    client.get(`/api/v1/collections/price-history/${productId}/`)
      .then(r => setHistory(r.data.history || r.data || []))
      .catch(() => {})
  }, [productId])
  return history
}
export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const addToCart = useCartStore(s => s.addItem)

  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState(0)
  const [selectedOptions, setSelectedOptions] = useState({}) // { Color: "Red", Size: "M" }
  const [quantity, setQuantity] = useState(1)
  const socialProof = useSocialProof(id)
  const flashSale = useFlashSaleForProduct(id)
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
    if (id) trackInteraction(id, INTERACTION_TYPES.VIEW)
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

  const handleShare = async () => {
    if (!product) return
    const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
    const url = window.location.href
    const text = `Encontrei isto na MICHA: ${product.title} por ${fmt(effectivePrice)}`
    haptic.light?.()
    if (navigator.share) {
      try {
        await navigator.share({ title: product.title, text, url })
        return
      } catch (e) {
        // user cancelled or unsupported — fall through to WhatsApp
        if (e?.name === 'AbortError') return
      }
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(`${text}\n${url}`)}`, '_blank')
  }

  const handleWishlist = async () => {
    setWishlisted(v => !v)
    if (!wishlisted) {
      trackWishlistAdd(product)
      await watchPrice(product)
    }
  }

  const variantAxes = product?.variant_axes || []
  const variantCombos = product?.variant_combos || []
  const hasVariants = variantAxes.length > 0
  const selectedCombo = hasVariants ? findMatchingCombo(variantCombos, selectedOptions) : null
  const variantsComplete = !hasVariants || !!selectedCombo
  // Bulk-pricing tiers (only apply when no variant + no flash sale)
  const priceTiers = (product?.price_tiers || []).slice().sort((a, b) => a.min_quantity - b.min_quantity)
  const hasTiers = priceTiers.length > 0 && !selectedCombo

  const tierUnitPrice = (qty) => {
    if (!hasTiers) return null
    const match = [...priceTiers].reverse().find(t => qty >= Number(t.min_quantity))
    return match ? Number(match.unit_price) : null
  }
  const tierPrice = !flashSale && !selectedCombo ? tierUnitPrice(quantity) : null

  // Flash-sale price wins when no variant is selected
  const flashPrice = !selectedCombo && flashSale ? Number(flashSale.sale.sale_price) : null
  const effectivePrice = flashPrice ?? tierPrice ?? selectedCombo?.price ?? product?.price
  const effectiveStock = selectedCombo?.quantity ?? product?.quantity

  const handleVariantSelect = (axisName, value) => {
    setSelectedOptions(prev => ({ ...prev, [axisName]: value }))
  }

  const handleAddToCart = async () => {
    if (hasVariants && !selectedCombo) {
      haptic.warning?.()
      const missing = variantAxes.find(a => !selectedOptions[a.name])
      alert(`Por favor selecione ${missing?.name?.toLowerCase() || 'as variantes'}.`)
      return
    }
    addToCart({ ...product, quantity, variant_combo_id: selectedCombo?.id, options: selectedOptions })
    trackCartAdd(product)
    setAddedToCart(true)
    setTimeout(() => setAddedToCart(false), 2000)
    client.post('/api/v1/cart/add/', {
      product_id: product.id,
      quantity,
      ...(selectedCombo ? { variant_combo_id: selectedCombo.id } : {}),
    }).catch((err) => {
      const msg = err?.response?.data?.detail || err?.response?.data?.variant_combo_id?.[0]
      if (msg) alert(msg)
    })
  }

  const handleBuyNow = async () => {
    if (hasVariants && !selectedCombo) {
      haptic.warning?.()
      const missing = variantAxes.find(a => !selectedOptions[a.name])
      alert(`Por favor selecione ${missing?.name?.toLowerCase() || 'as variantes'}.`)
      return
    }
    addToCart({ ...product, quantity, variant_combo_id: selectedCombo?.id, options: selectedOptions })
    await client.post('/api/v1/cart/add/', {
      product_id: product.id,
      quantity,
      ...(selectedCombo ? { variant_combo_id: selectedCombo.id } : {}),
    }).catch(() => {})
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

            {/* Share */}
            <button onClick={handleShare} aria-label="Partilhar"
              style={{ position: 'absolute', top: 16, right: 60, width: 36, height: 36, borderRadius: '50%', background: 'rgba(0,0,0,0.5)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="5" r="3" />
                <circle cx="6" cy="12" r="3" />
                <circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
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
              {Number(effectivePrice).toLocaleString()} Kz
            </span>
            <PersonalisedPriceBadge productId={product?.id} currentPrice={Number(effectivePrice)} />
        {product?.original_price && (
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

          {/* Bulk pricing tiers */}
          {hasTiers && (
            <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, padding: 12, marginBottom: 12 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                💰 Preços por quantidade
              </p>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {/* Base tier (1 unit) */}
                <div style={{
                  padding: '8px 12px', borderRadius: 10,
                  border: `1px solid ${quantity < (priceTiers[0]?.min_quantity || 999) ? '#C9A84C' : '#2A2A2A'}`,
                  background: quantity < (priceTiers[0]?.min_quantity || 999) ? 'rgba(201,168,76,0.08)' : 'transparent',
                  textAlign: 'center', minWidth: 70,
                }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A', margin: 0 }}>1 un</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C', margin: '2px 0 0' }}>
                    {Number(product.price).toLocaleString()} Kz
                  </p>
                </div>
                {priceTiers.map((tier, i) => {
                  const isActive = quantity >= Number(tier.min_quantity) &&
                    (i === priceTiers.length - 1 || quantity < Number(priceTiers[i + 1].min_quantity))
                  const savings = Math.round((1 - Number(tier.unit_price) / Number(product.price)) * 100)
                  return (
                    <div key={tier.id} style={{
                      padding: '8px 12px', borderRadius: 10,
                      border: `1px solid ${isActive ? '#C9A84C' : '#2A2A2A'}`,
                      background: isActive ? 'rgba(201,168,76,0.08)' : 'transparent',
                      textAlign: 'center', minWidth: 70, position: 'relative',
                    }}>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A', margin: 0 }}>
                        {tier.min_quantity}+ un
                      </p>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C', margin: '2px 0 0' }}>
                        {Number(tier.unit_price).toLocaleString()} Kz
                      </p>
                      {savings > 0 && (
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: '#059669', margin: '1px 0 0', fontWeight: 600 }}>
                          −{savings}%
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Flash sale badge */}
          <FlashSaleBadge flash={flashSale} />

          {/* Live social proof */}
          <SocialProofStrip proof={socialProof} />

          {/* SPU/SKU: "Available from N other sellers" pill */}
          {product.product_group_id && product.other_offers_count > 0 && (
            <button
              onClick={() => {
                const el = document.getElementById('other-offers-rail')
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', borderRadius: 20,
                border: '1px solid rgba(59,130,246,0.3)',
                background: 'rgba(59,130,246,0.08)',
                cursor: 'pointer', marginBottom: 16,
                fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#60a5fa',
              }}>
              🏬 Mais {product.other_offers_count} {product.other_offers_count === 1 ? 'loja oferece' : 'lojas oferecem'} este produto
              {product.other_offers_best_price && Number(product.other_offers_best_price) < Number(effectivePrice) && (
                <span style={{ fontWeight: 700, marginLeft: 4 }}>
                  desde {Number(product.other_offers_best_price).toLocaleString()} Kz
                </span>
              )}
            </button>
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

          {/* R4 trust signal — visible above the variant picker so it
              registers BEFORE the buyer commits to a purchase decision.
              Conversion benchmark on AO marketplaces: +12% w/ this. */}
          <BuyerTrustBanner />

          {/* Variant picker (replaces legacy size/color UI) */}
          <VariantPicker
            axes={variantAxes}
            combos={variantCombos}
            selectedOptions={selectedOptions}
            onSelect={handleVariantSelect}
          />

          {/* Combo stock indicator */}
          {selectedCombo && (
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: effectiveStock <= 5 ? '#dc2626' : '#9A9A9A', marginBottom: 16 }}>
              {effectiveStock > 0 ? `${effectiveStock} disponíveis` : 'Esgotado'}
            </p>
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
              { v: 'qa', l: 'Perguntas' },
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
              <ReviewsSection productId={id} />
            </div>
          )}

          {/* R4 seller mini-card + brand protected badge — visible above
              the bottom-of-page tabs so trust signals land before the
              user goes back to the sticky add-to-cart. */}
          {product?.store && (
            <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {product.brand_protected && (
                <BrandProtectedBadge brand={product.brand} />
              )}
              <SellerMiniCard
                store={product.store}
                trustBadge={product.seller_trust_badge}
                responseTime={
                  product.store.avg_response_minutes
                  ? `Responde em ~${Math.max(1, Math.round(product.store.avg_response_minutes))}min`
                  : null
                }
              />
            </div>
          )}

          {activeTab === 'qa' && (
            <div style={{ marginBottom: 24 }}>
              <ProductQASection productId={id} />
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

          {/* Other sellers offering the same product (SPU/SKU) */}
          {product.product_group_id && product.other_offers_count > 0 && (
            <div id="other-offers-rail" style={{ margin: '8px -16px 8px' }}>
              <OtherOffersRail
                groupId={product.product_group_id}
                currentProductId={product.id}
                currentPrice={Number(effectivePrice)}
              />
            </div>
          )}

          {/* Frequently bought together */}
          <div style={{ margin: '8px -16px 8px' }}>
            <ProductRail
              title="Comprados juntos"
              icon="🛒"
              endpoint={`/api/v1/recommendations/frequently-bought/${id}/`}
            />
          </div>

          {/* Recently viewed */}
          <div style={{ margin: '8px -16px 8px' }}>
            <ProductRail
              title="Vistos recentemente"
              icon="🕒"
              endpoint="/api/v1/recommendations/recently-viewed/"
              params={{ exclude: id, limit: 12 }}
              minItems={3}
            />
          </div>

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
    
      {product && (
        <div style={{ padding: '0 16px 8px', display: 'flex', gap: 8 }}>
          <ReportButton targetType="product" targetId={product.id} targetName={product.title} />
          <BlockUserButton userId={product.store?.owner} username={product.store?.name} />
        </div>
      )}
      <HelperBot screen="product" isSeller={false} />
      </BuyerLayout>
  )
}
