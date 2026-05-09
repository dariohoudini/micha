import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import HelperBot from '@/components/shared/HelperBot'
import SwipeToDelete from '@/components/shared/SwipeToDelete'
import { haptic } from '@/hooks/useUX'
import { useAuthStore } from '@/stores/authStore'

const fmt = (n) => Number(n || 0).toLocaleString() + ' Kz'

// Shipping cost estimate hook — calls real API then falls back to 1500
function useShippingEstimate(items, province) {
  const [cost, setCost] = useState(1500)
  useEffect(() => {
    if (!items?.length || !province) return
    client.post('/api/v1/shipping/estimate/', {
      province,
      items: items.map(i => ({ product_id: i.product?.id || i.id, quantity: i.quantity || 1 })),
    })
      .then(r => setCost(r.data.cost || 1500))
      .catch(() => setCost(1500))
  }, [items?.length, province])
  return cost
}

export function CartPage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(null)

  const province = user?.province || 'Luanda'
  const delivery = useShippingEstimate(items, province)

  useEffect(() => {
    client.get('/api/v1/cart/')
      .then(res => setItems(res.data.items || res.data || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  const updateQty = async (itemId, qty) => {
    if (qty < 1) return remove(itemId)
    setUpdating(itemId)
    try {
      await client.patch(`/api/v1/cart/items/${itemId}/`, { quantity: qty })
      setItems(prev => prev.map(i => i.id === itemId ? { ...i, quantity: qty } : i))
    } catch {} finally { setUpdating(null) }
  }

  const remove = async (itemId) => {
    haptic.light?.()
    try {
      await client.delete(`/api/v1/cart/items/${itemId}/remove/`)
      setItems(prev => prev.filter(i => i.id !== itemId))
    } catch { setItems(prev => prev.filter(i => i.id !== itemId)) }
  }

  const subtotal = items.reduce((sum, i) => sum + Number(i.price || i.product?.price || 0) * (i.quantity || 1), 0)
  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <BuyerLayout>
      <div style={{ padding: '52px 16px 12px', flexShrink: 0 }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Carrinho</h1>
        {items.length > 0 && <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>{items.length} {items.length === 1 ? 'item' : 'itens'}</p>}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
          </div>
        ) : items.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '50%', gap: 16 }}>
            <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>O seu carrinho está vazio.</p>
            <button onClick={() => navigate('/explore')} style={{ padding: '10px 24px', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>Explorar produtos</button>
          </div>
        ) : (
          <div style={{ padding: '16px 16px 120px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {items.map(item => {
              const product = item.product || item
              const price = Number(item.price || product.price || 0)
              return (
                <SwipeToDelete key={item.id} onDelete={() => remove(item.id)} deleteLabel="Remover">
                  <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14, display: 'flex', gap: 12 }}>
                    <div style={{ width: 70, height: 70, borderRadius: 10, background: '#1E1E1E', flexShrink: 0, overflow: 'hidden' }}>
                      {(item.variant_image || item.product_image || product.image_url || product.images?.[0]?.image) && (
                        <img src={item.variant_image || item.product_image || product.image_url || product.images[0].image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ ...S, fontSize: 13, fontWeight: 500, color: '#FFFFFF', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.product_title || product.name || product.title}
                      </p>
                      {item.variant_options && Object.keys(item.variant_options).length > 0 && (
                        <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 4 }}>
                          {Object.entries(item.variant_options).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                        </p>
                      )}
                      <p style={{ ...S, fontSize: 14, fontWeight: 700, color: '#C9A84C', marginBottom: 8 }}>{fmt(price)}</p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', background: '#1E1E1E', borderRadius: 10, border: '1px solid #2A2A2A' }}>
                          <button onClick={() => updateQty(item.id, (item.quantity || 1) - 1)} style={{ width: 32, height: 32, background: 'none', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 16 }}>−</button>
                          <span style={{ ...S, fontSize: 13, fontWeight: 600, color: '#FFFFFF', minWidth: 24, textAlign: 'center' }}>{updating === item.id ? '…' : (item.quantity || 1)}</span>
                          <button onClick={() => updateQty(item.id, (item.quantity || 1) + 1)} style={{ width: 32, height: 32, background: 'none', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 16 }}>+</button>
                        </div>
                        <button onClick={() => remove(item.id)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /></svg>
                        </button>
                      </div>
                    </div>
                  </div>
                </SwipeToDelete>
              )
            })}
            <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16 }}>
              {[{ label: 'Subtotal', value: fmt(subtotal) }, { label: 'Entrega', value: fmt(delivery) }].map(row => (
                <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>{row.label}</span>
                  <span style={{ ...S, fontSize: 13, color: '#FFFFFF' }}>{row.value}</span>
                </div>
              ))}
              <div style={{ borderTop: '1px solid #1E1E1E', paddingTop: 10, display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
                <span style={{ ...S, fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>{fmt(subtotal + delivery)}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {items.length > 0 && (
        <div style={{ padding: '14px 16px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
          <button
            onClick={() => { haptic.medium?.(); navigate('/checkout', { state: { cartItems: items, total: subtotal + delivery } }) }}
            style={{ width: '100%', padding: '15px 0', borderRadius: 14, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            Finalizar — {fmt(subtotal + delivery)}
          </button>
        </div>
      )}

      <HelperBot screen="cart" isSeller={false} />
    </BuyerLayout>
  )
}

export default CartPage
