import { useNavigate } from 'react-router-dom'
import { useCartStore as useCart } from '@/stores/cartStore'
import BottomNav from '@/components/shared/BottomNav'
import { formatPrice } from '@/components/buyer/mockData'

export default function CartPage() {
  const navigate = useNavigate()
  const items = useCart(s => s.items); const totalItems = useCart(s => s.totalItems); const totalPrice = useCart(s => s.totalPrice); const incrementItem = useCart(s => s.incrementItem); const decrementItem = useCart(s => s.decrementItem); const removeItem = useCart(s => s.removeItem); const clearCart = useCart(s => s.clearCart)

  const delivery = items.length > 0 && items.every(i => i.express) ? 0 : items.length > 0 ? 1500 : 0
  const total = totalPrice + delivery

  if (items.length === 0) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
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
        <BottomNav />
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 16px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>Carrinho ({totalItems})</h1>
        <button onClick={clearCart} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', background: 'none', border: 'none', cursor: 'pointer' }}>Limpar</button>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '0 16px' }}>
          {items.map(item => (
            <div key={item.id} style={{ display: 'flex', gap: 14, alignItems: 'center', background: '#1E1E1E', borderRadius: 16, border: '1px solid #2A2A2A', padding: 14 }}>
              <div style={{ width: 72, height: 72, borderRadius: 12, flexShrink: 0, background: item.image_color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                </svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', lineHeight: 1.3, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 8 }}>{item.seller}</p>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(item.price)}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <button onClick={() => decrementItem(item.id)} style={{ width: 28, height: 28, borderRadius: 8, background: '#2A2A2A', border: 'none', color: '#FFFFFF', fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>−</button>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#FFFFFF', minWidth: 16, textAlign: 'center' }}>{item.quantity}</span>
                    <button onClick={() => incrementItem(item.id)} style={{ width: 28, height: 28, borderRadius: 8, background: '#C9A84C', border: 'none', color: '#0A0A0A', fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>+</button>
                  </div>
                </div>
              </div>
              <button onClick={() => removeItem(item.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                </svg>
              </button>
            </div>
          ))}

          {/* Summary */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #2A2A2A', padding: 16, marginTop: 4 }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 14 }}>Resumo do pedido</h3>
            {[{ label: 'Subtotal', value: formatPrice(totalPrice) }, { label: 'Entrega', value: delivery === 0 ? 'Grátis' : formatPrice(delivery) }].map(row => (
              <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{row.label}</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: row.label === 'Entrega' && delivery === 0 ? '#059669' : '#FFFFFF' }}>{row.value}</span>
              </div>
            ))}
            <div style={{ height: 1, background: '#2A2A2A', margin: '12px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(total)}</span>
            </div>
          </div>

          {delivery === 0 && (
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 12, padding: '10px 14px' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="#C9A84C"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C' }}>Entrega Express gratuita incluída!</span>
            </div>
          )}
          <div style={{ height: 8 }} />
        </div>
      </div>

      <div style={{ padding: '12px 16px 32px', background: '#0A0A0A', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
        <button className="btn-primary" onClick={() => navigate('/checkout')}>Finalizar Compra · {formatPrice(total)}</button>
      </div>
      <BottomNav />
    </div>
  )
}
