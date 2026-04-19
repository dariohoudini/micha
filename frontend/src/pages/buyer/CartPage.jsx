import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import { useCartStore } from '@/stores/cartStore'
import { formatPrice } from '@/components/buyer/mockData'

export default function CartPage() {
  const navigate = useNavigate()
  const items = useCartStore(s => s.items)
  const totalPrice = useCartStore(s => s.totalPrice)
  const incrementItem = useCartStore(s => s.incrementItem)
  const decrementItem = useCartStore(s => s.decrementItem)
  const removeItem = useCartStore(s => s.removeItem)
  const clearCart = useCartStore(s => s.clearCart)
  const [coupon, setCoupon] = useState('')
  const [couponApplied, setCouponApplied] = useState(false)
  const [couponError, setCouponError] = useState('')

  const totalItems = items.reduce((a, i) => a + i.quantity, 0)
  const delivery = items.length > 0 && items.every(i => i.express) ? 0 : items.length > 0 ? 1500 : 0
  const discount = couponApplied ? Math.round(totalPrice * 0.1) : 0
  const total = totalPrice + delivery - discount

  // Group items by seller
  const grouped = items.reduce((acc, item) => {
    const s = item.seller || 'Outros'
    if (!acc[s]) acc[s] = []
    acc[s].push(item)
    return acc
  }, {})

  const handleCoupon = () => {
    if (coupon.toUpperCase() === 'MICHA10') {
      setCouponApplied(true); setCouponError('')
    } else {
      setCouponError('Código inválido ou expirado.'); setCouponApplied(false)
    }
  }

  if (items.length === 0) {
    return (
      <BuyerLayout>
        <div style={{ padding: '52px 16px 16px', flexShrink: 0 }}>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>Carrinho</h1>
        </div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, padding: '0 32px' }}>
          <div style={{ width: 80, height: 80, borderRadius: 20, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" /><line x1="3" y1="6" x2="21" y2="6" /><path d="M16 10a4 4 0 0 1-8 0" />
            </svg>
          </div>
          <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', textAlign: 'center' }}>Carrinho vazio</h2>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>Adicione produtos para começar a sua compra</p>
          <button className="btn-primary" onClick={() => navigate('/home')} style={{ marginTop: 8 }}>Explorar produtos</button>
        </div>
      </BuyerLayout>
    )
  }

  return (
    <BuyerLayout>
      <div style={{ padding: '52px 16px 12px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Carrinho ({totalItems})</h1>
        <button onClick={clearCart} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', background: 'none', border: 'none', cursor: 'pointer' }}>Limpar</button>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '0 16px 20px' }}>

          {/* Items grouped by seller */}
          {Object.entries(grouped).map(([seller, sellerItems]) => (
            <div key={seller} style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
              {/* Seller header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderBottom: '1px solid #1E1E1E' }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                </svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#C9A84C' }}>{seller}</span>
              </div>

              {/* Items */}
              {sellerItems.map(item => (
                <div key={item.id} style={{ display: 'flex', gap: 12, padding: 14, borderBottom: '1px solid #1E1E1E' }}>
                  <div style={{ width: 70, height: 70, borderRadius: 10, background: item.image_color, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                    </svg>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', lineHeight: 1.3, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                      {item.name}
                    </p>
                    {item.express && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 3, marginBottom: 6 }}>
                        <svg width="9" height="9" viewBox="0 0 24 24" fill="#C9A84C"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: '#C9A84C', fontWeight: 600 }}>EXPRESS</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(item.price)}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <button onClick={() => decrementItem(item.id)} style={{ width: 26, height: 26, borderRadius: 6, background: '#2A2A2A', border: 'none', color: '#FFFFFF', fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>−</button>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#FFFFFF', minWidth: 14, textAlign: 'center' }}>{item.quantity}</span>
                        <button onClick={() => incrementItem(item.id)} style={{ width: 26, height: 26, borderRadius: 6, background: '#C9A84C', border: 'none', color: '#0A0A0A', fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>+</button>
                      </div>
                    </div>
                  </div>
                  <button onClick={() => removeItem(item.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0, alignSelf: 'flex-start' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          ))}

          {/* Coupon */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 14 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 10 }}>Código promocional</p>
            <div style={{ display: 'flex', gap: 8 }}>
              <input className="input-base" placeholder="Insira o código" value={coupon} onChange={e => { setCoupon(e.target.value.toUpperCase()); setCouponError(''); setCouponApplied(false) }}
                style={{ flex: 1, textTransform: 'uppercase' }} disabled={couponApplied} />
              <button onClick={handleCoupon} disabled={couponApplied || !coupon}
                style={{ padding: '0 16px', borderRadius: 12, background: couponApplied ? '#059669' : '#C9A84C', border: 'none', color: '#0A0A0A', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, cursor: 'pointer', flexShrink: 0, opacity: (!coupon && !couponApplied) ? 0.5 : 1 }}>
                {couponApplied ? '✓' : 'Aplicar'}
              </button>
            </div>
            {couponError && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171', marginTop: 6 }}>{couponError}</p>}
            {couponApplied && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669', marginTop: 6 }}>Desconto de 10% aplicado!</p>}
          </div>

          {/* Order summary */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 14 }}>Resumo do pedido</h3>
            {[
              { label: 'Subtotal', value: formatPrice(totalPrice) },
              { label: 'Entrega', value: delivery === 0 ? 'Grátis' : formatPrice(delivery), green: delivery === 0 },
              ...(couponApplied ? [{ label: 'Desconto (MICHA10)', value: `-${formatPrice(discount)}`, green: true }] : []),
            ].map(row => (
              <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{row.label}</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: row.green ? '#059669' : '#FFFFFF' }}>{row.value}</span>
              </div>
            ))}
            <div style={{ height: 1, background: '#2A2A2A', margin: '12px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(total)}</span>
            </div>
          </div>

          {delivery === 0 && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 12, padding: '10px 14px' }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="#C9A84C"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C' }}>Entrega Express gratuita incluída!</span>
            </div>
          )}
        </div>
      </div>

      <div style={{ padding: '12px 16px', background: '#0A0A0A', borderTop: '1px solid #1E1E1E', flexShrink: 0, paddingBottom: 'max(24px, env(safe-area-inset-bottom))' }}>
        <button className="btn-primary" onClick={() => navigate('/checkout')}>
          Finalizar Compra · {formatPrice(total)}
        </button>
      </div>
    </BuyerLayout>
  )
}
