import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import OrderSuccessAnimation from '@/components/shared/OrderSuccessAnimation'
import { SocialOrderShareCard } from '@/components/shared/MichaUXComponents'
import { haptic } from '@/hooks/useUX'
import trackInteraction, { INTERACTION_TYPES } from '@/api/tracking'
import client from '@/api/client'

const GOLD = '#C9A84C', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A', CARD = '#1E1E1E', BORDER = '#2A2A2A', GREEN = '#059669'
const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const S = { fontFamily: "'DM Sans', sans-serif" }

const STEPS = [
  { icon: '✅', label: 'Pedido recebido', done: true },
  { icon: '📦', label: 'Vendedor a preparar', done: false },
  { icon: '🚚', label: 'Em entrega', done: false },
  { icon: '🏠', label: 'Entregue', done: false },
]

export default function OrderConfirmedPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const orderId = location.state?.orderId || location.state?.order_id || null
  const total = location.state?.total
  const [showShare, setShowShare] = useState(false)
  const [loyaltyPoints, setLoyaltyPoints] = useState(null)
  const [orderDetails, setOrderDetails] = useState(null)

  useEffect(() => {
    haptic.success?.()
    if (orderId) trackInteraction(null, INTERACTION_TYPES.PURCHASE, { order_id: orderId })
    setTimeout(() => setShowShare(true), 2500)

    if (orderId) {
      client.get(`/api/v1/orders/${orderId}/`)
        .then(r => setOrderDetails(r.data))
        .catch(() => {})
    }
    client.get('/api/v1/loyalty/balance/')
      .then(r => setLoyaltyPoints(r.data?.points || r.data?.balance || null))
      .catch(() => {})
  }, [])

  const displayId = orderId ? String(orderId).slice(0, 8).toUpperCase() : 'MC-XXXXXX'
  const earnedPoints = total ? Math.floor(Number(total) / 1000) : null

  return (
    <BuyerLayout title="Pedido confirmado">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 24px 80px', textAlign: 'center' }}>

        <OrderSuccessAnimation onDone={() => {}} />

        {/* Order ID + total */}
        <div style={{ marginTop: 8, marginBottom: 24 }}>
          <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 8px' }}>Pedido confirmado!</p>
          <p style={{ ...S, fontSize: 14, color: MUTED, margin: '0 0 4px' }}>Número do pedido</p>
          <p style={{ ...S, fontSize: 16, fontWeight: 600, color: GOLD, margin: 0 }}>#{displayId}</p>
          {total && (
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: TEXT, margin: '8px 0 0' }}>{fmt(total)}</p>
          )}
        </div>

        {/* Loyalty points earned */}
        {earnedPoints > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 12, padding: '10px 16px', width: '100%', marginBottom: 16 }}>
            <span style={{ fontSize: 20 }}>🌟</span>
            <div style={{ textAlign: 'left', flex: 1 }}>
              <p style={{ ...S, fontSize: 13, fontWeight: 600, color: GOLD }}>+{earnedPoints} pontos ganhos!</p>
              <p style={{ ...S, fontSize: 11, color: MUTED }}>
                {loyaltyPoints !== null ? `Saldo total: ${loyaltyPoints + earnedPoints} pontos` : 'Adicionados à sua carteira de fidelidade'}
              </p>
            </div>
            <button onClick={() => navigate('/profile')} style={{ ...S, fontSize: 11, color: GOLD, background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}>Ver →</button>
          </div>
        )}

        {/* Order items preview */}
        {orderDetails?.items?.length > 0 && (
          <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 14, width: '100%', marginBottom: 16, textAlign: 'left' }}>
            <p style={{ ...S, fontSize: 12, color: MUTED, marginBottom: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Resumo</p>
            {orderDetails.items.slice(0, 3).map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, background: '#2A2A2A', overflow: 'hidden', flexShrink: 0 }}>
                  {item.product?.image_url && <img src={item.product.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                </div>
                <p style={{ ...S, fontSize: 12, color: TEXT, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.product?.name || item.name} × {item.quantity}
                </p>
                <span style={{ ...S, fontSize: 12, color: MUTED, flexShrink: 0 }}>{fmt(item.total_price || item.price)}</span>
              </div>
            ))}
            {orderDetails.items.length > 3 && (
              <p style={{ ...S, fontSize: 11, color: MUTED, textAlign: 'center', marginTop: 4 }}>+{orderDetails.items.length - 3} mais itens</p>
            )}
          </div>
        )}

        {/* Steps */}
        <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 16, width: '100%', marginBottom: 16 }}>
          {STEPS.map((step, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: i < STEPS.length - 1 ? `1px solid ${BORDER}` : 'none' }}>
              <span style={{ fontSize: 18 }}>{step.icon}</span>
              <p style={{ ...S, fontSize: 13, color: step.done ? GREEN : MUTED, margin: 0, fontWeight: step.done ? 600 : 400 }}>{step.label}</p>
              {step.done && <span style={{ marginLeft: 'auto', ...S, fontSize: 11, color: GREEN }}>Agora</span>}
            </div>
          ))}
        </div>

        {/* Share card */}
        {showShare && (
          <div style={{ width: '100%', marginBottom: 16 }}>
            <SocialOrderShareCard order={{ items: `Pedido #${displayId}` }} />
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: '100%' }}>
          <button
            onClick={() => navigate(orderId ? `/orders/${orderId}` : '/orders')}
            style={{ padding: 14, borderRadius: 14, border: 'none', background: GOLD, color: '#000', ...S, fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
          >
            Acompanhar pedido
          </button>
          <button
            onClick={() => navigate('/home')}
            style={{ padding: 14, borderRadius: 14, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, ...S, fontSize: 14, cursor: 'pointer' }}
          >
            Continuar a comprar
          </button>
        </div>
      </div>
    </BuyerLayout>
  )
}
