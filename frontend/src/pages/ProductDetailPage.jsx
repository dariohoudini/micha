import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useCartStore as useCart } from '@/stores/cartStore'
import { MOCK_PRODUCTS, formatPrice } from '@/components/buyer/mockData'

export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const addItem = useCart(s => s.addItem); const totalItems = useCart(s => s.totalItems)
  const [wishlist, setWishlist] = useState(false)
  const [quantity, setQuantity] = useState(1)
  const [added, setAdded] = useState(false)

  const product = MOCK_PRODUCTS.find(p => p.id === id) || MOCK_PRODUCTS[0]
  const discount = product.original_price
    ? Math.round((1 - product.price / product.original_price) * 100)
    : null

  const handleAddToCart = () => {
    addItem(product, quantity)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>

      {/* Product image */}
      <div style={{
        height: 320, background: product.image_color,
        position: 'relative', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {/* Placeholder */}
        <div style={{
          width: 120, height: 120, borderRadius: '50%',
          background: 'rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none"
            stroke="rgba(255,255,255,0.2)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </div>

        {/* Back button */}
        <button onClick={() => navigate(-1)}
          style={{
            position: 'absolute', top: 52, left: 16,
            width: 38, height: 38, borderRadius: 12,
            background: 'rgba(0,0,0,0.5)', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>

        {/* Wishlist */}
        <button onClick={() => setWishlist(v => !v)}
          style={{
            position: 'absolute', top: 52, right: 16,
            width: 38, height: 38, borderRadius: 12,
            background: 'rgba(0,0,0,0.5)', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
          <svg width="18" height="18" viewBox="0 0 24 24"
            fill={wishlist ? '#C9A84C' : 'none'}
            stroke={wishlist ? '#C9A84C' : '#FFFFFF'} strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
          </svg>
        </button>

        {/* Express badge */}
        {product.express && (
          <div style={{
            position: 'absolute', bottom: 16, left: 16,
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'rgba(201,168,76,0.15)',
            border: '1px solid rgba(201,168,76,0.4)',
            padding: '6px 12px', borderRadius: 20,
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: '#C9A84C' }}>
              ENTREGA EXPRESS
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '20px 20px 0' }}>

          {/* Seller */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', fontWeight: 500 }}>
              {product.seller}
            </span>
            {product.seller_verified && (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
          </div>

          {/* Name */}
          <h1 style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 24, fontWeight: 700, color: '#FFFFFF',
            lineHeight: 1.3, marginBottom: 12,
          }}>
            {product.name}
          </h1>

          {/* Rating + sold */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {[1,2,3,4,5].map(i => (
                <svg key={i} width="13" height="13" viewBox="0 0 24 24"
                  fill={i <= Math.round(product.rating) ? '#C9A84C' : '#2A2A2A'}>
                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                </svg>
              ))}
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginLeft: 4 }}>
                {product.rating} ({product.reviews} avaliações)
              </span>
            </div>
          </div>

          {/* Price */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 20 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 26, fontWeight: 700, color: '#C9A84C' }}>
              {formatPrice(product.price)}
            </span>
            {product.original_price && (
              <>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: '#9A9A9A', textDecoration: 'line-through' }}>
                  {formatPrice(product.original_price)}
                </span>
                <span style={{
                  fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700,
                  color: '#FFFFFF', background: '#dc2626',
                  padding: '2px 7px', borderRadius: 6,
                }}>
                  -{discount}%
                </span>
              </>
            )}
          </div>

          {/* Divider */}
          <div style={{ height: 1, background: '#1E1E1E', marginBottom: 20 }} />

          {/* Quantity */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF', fontWeight: 500 }}>
              Quantidade
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <button
                onClick={() => setQuantity(q => Math.max(1, q - 1))}
                style={{
                  width: 32, height: 32, borderRadius: 10,
                  background: '#1E1E1E', border: '1px solid #2A2A2A',
                  color: '#FFFFFF', fontSize: 18, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                −
              </button>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#FFFFFF', minWidth: 20, textAlign: 'center' }}>
                {quantity}
              </span>
              <button
                onClick={() => setQuantity(q => q + 1)}
                style={{
                  width: 32, height: 32, borderRadius: 10,
                  background: '#C9A84C', border: 'none',
                  color: '#0A0A0A', fontSize: 18, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 700,
                }}>
                +
              </button>
            </div>
          </div>

          {/* Description placeholder */}
          <div style={{
            background: '#141414', borderRadius: 14,
            padding: 16, marginBottom: 20,
          }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 8 }}>
              Descrição
            </h3>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', lineHeight: 1.6 }}>
              Produto de qualidade premium disponível no MICHA Express. Entrega rápida em toda Angola. Vendido por {product.seller}.
            </p>
          </div>

          {/* Delivery info */}
          <div style={{
            background: '#141414', borderRadius: 14,
            padding: 16, marginBottom: 24,
            display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            {[
              { icon: '⚡', label: product.express ? 'Entrega Express disponível' : 'Entrega Standard', sub: product.express ? 'Receba hoje em Luanda' : 'Entrega em 2-5 dias úteis' },
              { icon: '🔄', label: 'Devoluções gratuitas', sub: 'Em até 15 dias após a entrega' },
              { icon: '🔒', label: 'Compra segura', sub: 'Pagamento via Multicaixa Express' },
            ].map((item, i) => (
              <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <span style={{ fontSize: 18 }}>{item.icon}</span>
                <div>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF' }}>{item.label}</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 1 }}>{item.sub}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Add to cart bar */}
      <div style={{
        padding: '12px 16px 32px',
        background: '#0A0A0A',
        borderTop: '1px solid #1E1E1E',
        flexShrink: 0,
      }}>
        <button
          className="btn-primary"
          onClick={handleAddToCart}
          style={{
            background: added ? '#059669' : '#C9A84C',
            transition: 'background 0.3s ease',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}
        >
          {added ? (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Adicionado ao carrinho!
            </>
          ) : (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <path d="M16 10a4 4 0 0 1-8 0" />
              </svg>
              Adicionar ao Carrinho · {formatPrice(product.price * quantity)}
            </>
          )}
        </button>
      </div>
    </div>
  )
}
