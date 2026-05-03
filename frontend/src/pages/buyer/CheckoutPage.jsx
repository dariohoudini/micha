import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { DeliverySlotPicker, GuestCheckoutOption, SplitPaymentUI } from '@/components/shared/MichaUXComponents'
import { CheckoutProgressBar, MulticaixaPaymentUI, OrderSummary, SavedAddresses, PromoCodeInput } from '@/components/buyer/CheckoutUX'
import { haptic } from '@/hooks/useUX'
import promotionsAPI from '@/api/promotions'

const PROVINCES = ['Luanda','Benguela','Huambo','Huíla','Cabinda','Uíge','Namibe','Malanje','Bié','Kwanza Sul','Kwanza Norte']
const fmt = (n) => Number(n || 0).toLocaleString() + ' Kz'

export default function CheckoutPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore(s => s.user)
  const { cartItems = [], total = 0 } = location.state || {}

  const [address, setAddress] = useState({ province: user?.province || 'Luanda', municipality: '', neighbourhood: '', street: '', notes: '' })
  const [payment, setPayment] = useState('multicaixa')
  const [loading, setLoading] = useState(false)
  const [deliverySlot, setDeliverySlot] = useState(null)
  const [walletAmount, setWalletAmount] = useState(0)
  const [step, setStep] = useState(1)
  const [error, setError] = useState(null)
  const [couponCode, setCouponCode] = useState('')
  const [couponLoading, setCouponLoading] = useState(false)
  const [couponResult, setCouponResult] = useState(null)

  const discountAmount = couponResult?.discount_amount || 0
  const finalTotal = Math.max(0, total - discountAmount)

  const handleApplyCoupon = async () => {
    if (!couponCode.trim()) return
    setCouponLoading(true)
    setCouponResult(null)
    try {
      const res = await promotionsAPI.validateCoupon(couponCode.trim())
      setCouponResult({ ...res.data, valid: true })
      haptic.success?.()
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Código inválido ou expirado.'
      setCouponResult({ valid: false, error: msg })
    } finally {
      setCouponLoading(false) }
  }

  const handleCheckout = async () => {
    if (!address.province || !address.municipality) { setError('Preencha a província e o município.'); return }
    setLoading(true)
    setError(null)
    try {
      const res = await client.post('/api/v1/orders/checkout/', {
        delivery_address: [address.street, address.neighbourhood, address.municipality, address.province].filter(Boolean).join(', '),
        delivery_province: address.province,
        delivery_notes: address.notes,
        payment_method: payment,
        items: cartItems.map(i => ({ product: i.product?.id || i.id, quantity: i.quantity || 1 })),
        ...(couponResult?.valid ? { coupon_code: couponCode.trim() } : {}),
      })
      navigate('/order-confirmed', { state: { orderId: res.data?.id || res.data?.order_id, total: finalTotal } })
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.error || 'Erro ao processar pedido.')
    } finally { setLoading(false) }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }
  const inputStyle = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 13, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>
      <CheckoutProgressBar step={step} />
      <div style={{ padding: '0 16px 16px', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Finalizar pedido</h1>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '8px 16px 120px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div>
            <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>📍 Endereço de entrega</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <select value={address.province} onChange={e => setAddress(p => ({ ...p, province: e.target.value }))} style={inputStyle}>
                {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              {[{k:'municipality',p:'Município'},{k:'neighbourhood',p:'Bairro'},{k:'street',p:'Rua / Avenida'},{k:'notes',p:'Notas para o entregador (opcional)'}].map(f => (
                <input key={f.k} value={address[f.k]} onChange={e => setAddress(p => ({ ...p, [f.k]: e.target.value }))} placeholder={f.p} style={inputStyle} />
              ))}
            </div>
          </div>

          <div>
            <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>💳 Método de pagamento</h2>
            {[{v:'multicaixa',l:'Multicaixa Express',d:'Pagamento instantâneo',i:'📱'},{v:'bank_transfer',l:'Transferência bancária',d:'Referência gerada após confirmar',i:'🏦'},{v:'cod',l:'Pagamento na entrega',d:'Disponível apenas em Luanda',i:'💵'}].map(m => (
              <button key={m.v} onClick={() => setPayment(m.v)}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderRadius: 12, border: `1.5px solid ${payment === m.v ? '#C9A84C' : '#1E1E1E'}`, background: payment === m.v ? 'rgba(201,168,76,0.08)' : '#141414', cursor: 'pointer', textAlign: 'left', width: '100%', marginBottom: 8 }}>
                <span style={{ fontSize: 22 }}>{m.i}</span>
                <div style={{ flex: 1 }}>
                  <p style={{ ...S, fontSize: 13, fontWeight: 500, color: '#FFFFFF', marginBottom: 2 }}>{m.l}</p>
                  <p style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>{m.d}</p>
                </div>
                {payment === m.v && <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg></div>}
              </button>
            ))}
          </div>

          <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16 }}>
            <h3 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 10 }}>Resumo</h3>
            {cartItems.slice(0, 3).map(item => {
              const product = item.product || item
              return (
                <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ ...S, fontSize: 12, color: '#9A9A9A', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name} × {item.quantity || 1}</span>
                  <span style={{ ...S, fontSize: 12, color: '#FFFFFF', marginLeft: 8 }}>{fmt(Number(item.price || product.price || 0) * (item.quantity || 1))}</span>
                </div>
              )
            })}
            <div style={{ borderTop: '1px solid #1E1E1E', paddingTop: 10, display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
              <span style={{ ...S, fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>{fmt(total)}</span>
            </div>
          </div>

          {/* Promo code */}
          <div>
            <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>🎟️ Código promocional</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={couponCode}
                onChange={e => { setCouponCode(e.target.value.toUpperCase()); setCouponResult(null) }}
                placeholder="CÓDIGO"
                style={{ ...inputStyle, flex: 1, letterSpacing: '0.08em', fontWeight: 600 }}
              />
              <button
                onClick={handleApplyCoupon}
                disabled={couponLoading || !couponCode.trim()}
                style={{ padding: '12px 18px', borderRadius: 12, border: 'none', background: couponLoading || !couponCode.trim() ? 'rgba(201,168,76,0.3)' : '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer', flexShrink: 0 }}
              >
                {couponLoading ? '...' : 'Aplicar'}
              </button>
            </div>
            {couponResult?.valid && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 10, padding: '10px 14px' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                <p style={{ ...S, fontSize: 13, color: '#059669', flex: 1 }}>{couponResult.message || 'Desconto aplicado!'}</p>
                <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#059669' }}>−{fmt(discountAmount)}</span>
              </div>
            )}
            {couponResult && !couponResult.valid && (
              <p style={{ ...S, fontSize: 12, color: '#ef4444', marginTop: 6 }}>{couponResult.error}</p>
            )}
          </div>

          {/* Updated total with discount */}
          {couponResult?.valid && discountAmount > 0 && (
            <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Subtotal</span>
                <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>{fmt(total)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ ...S, fontSize: 13, color: '#059669' }}>Desconto ({couponCode})</span>
                <span style={{ ...S, fontSize: 13, color: '#059669' }}>−{fmt(discountAmount)}</span>
              </div>
              <div style={{ borderTop: '1px solid #1E1E1E', paddingTop: 8, display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ ...S, fontSize: 15, fontWeight: 700, color: '#FFF' }}>Total a pagar</span>
                <span style={{ ...S, fontSize: 17, fontWeight: 700, color: '#C9A84C' }}>{fmt(finalTotal)}</span>
              </div>
            </div>
          )}

          {error && <div style={{ background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 10, padding: 12 }}><p style={{ ...S, fontSize: 13, color: '#ef4444' }}>{error}</p></div>}
        </div>
      </div>

      <div style={{ padding: '14px 16px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
        <button onClick={handleCheckout} disabled={loading}
          style={{ width: '100%', padding: '15px 0', borderRadius: 14, border: 'none', background: loading ? 'rgba(201,168,76,0.5)' : '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          {loading ? 'A processar...' : `Confirmar — ${fmt(finalTotal)}`}
        </button>
      </div>
    </div>
  )
}
