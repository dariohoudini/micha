import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useCartStore } from '@/stores/cartStore'
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
  const storeItems = useCartStore(s => s.items)
  const storeTotalPrice = useCartStore(s => s.totalPrice)
  const storeDelivery = storeItems.length > 0 && storeItems.every(i => i.express) ? 0 : storeItems.length > 0 ? 1500 : 0
  const { cartItems = storeItems, total = storeTotalPrice + storeDelivery } = location.state || {}

  const [address, setAddress] = useState({ province: user?.province || 'Luanda', municipality: '', neighbourhood: '', street: '', notes: '' })
  const [payment, setPayment] = useState('multicaixa')
  const [loading, setLoading] = useState(false)
  const [deliverySlot, setDeliverySlot] = useState(null)
  const [walletAmount, setWalletAmount] = useState(0)
  const [step, setStep] = useState(1)
  const [error, setError] = useState(null)
  const [couponCode, setCouponCode] = useState('')
  const [couponLoading, setCouponLoading] = useState(false)
  const [couponError, setCouponError] = useState('')
  const [appliedCoupons, setAppliedCoupons] = useState([]) // [{code, discount_amount, scope, seller_name, ...}]
  const [storeCredit, setStoreCredit] = useState(0)
  const [useCredit, setUseCredit] = useState(false)

  // Load buyer's loyalty balance once on mount
  useEffect(() => {
    client.get('/api/v1/auth/loyalty/')
      .then(r => setStoreCredit(Number(r.data.store_credit || 0)))
      .catch(() => {})
  }, [])

  const couponDiscount = appliedCoupons.reduce((sum, c) => sum + Number(c.discount_amount || 0), 0)
  // Cap credit at remaining total after coupons
  const subtotalAfterCoupons = Math.max(0, total - couponDiscount)
  const creditApplied = useCredit ? Math.min(storeCredit, subtotalAfterCoupons) : 0
  const discountAmount = couponDiscount + creditApplied
  const finalTotal = Math.max(0, total - discountAmount)

  const platformCount = appliedCoupons.filter(c => c.scope === 'platform').length
  const sellerSlotsTaken = new Set(appliedCoupons.filter(c => c.scope === 'seller').map(c => c.seller_id))

  const handleApplyCoupon = async () => {
    const code = couponCode.trim().toUpperCase()
    if (!code) return
    if (appliedCoupons.some(c => c.code === code)) {
      setCouponError('Cupão já aplicado.')
      return
    }
    setCouponLoading(true)
    setCouponError('')
    try {
      const res = await promotionsAPI.validateCoupon(code)
      const data = res.data
      // Stacking checks
      if (data.scope === 'platform' && platformCount >= 1) {
        setCouponError('Apenas um cupão da plataforma por compra.')
        setCouponLoading(false)
        return
      }
      if (data.scope === 'seller' && sellerSlotsTaken.has(data.seller_id)) {
        setCouponError('Já tens um cupão desta loja aplicado.')
        setCouponLoading(false)
        return
      }
      setAppliedCoupons(prev => [...prev, data])
      setCouponCode('')
      haptic.success?.()
    } catch (err) {
      setCouponError(err.response?.data?.detail || err.response?.data?.error || 'Código inválido ou expirado.')
    } finally {
      setCouponLoading(false)
    }
  }

  const removeCoupon = (code) => {
    setAppliedCoupons(prev => prev.filter(c => c.code !== code))
    setCouponError('')
  }

  const handleCheckout = async () => {
    if (!address.province || !address.municipality) { setError('Preencha a província e o município.'); return }
    setLoading(true)
    setError(null)
    try {
      // Compute device fingerprint (cached in localStorage). Failing this is
      // not fatal — backend treats missing fingerprint as a missing signal.
      let fingerprint = ''
      try {
        const { getFingerprint } = await import('@/api/fingerprint')
        fingerprint = await getFingerprint()
      } catch { /* ignore */ }

      const res = await client.post('/api/v1/orders/checkout/', {
        delivery_address: [address.street, address.neighbourhood, address.municipality, address.province].filter(Boolean).join(', '),
        delivery_province: address.province,
        delivery_notes: address.notes,
        payment_method: payment,
        items: cartItems.map(i => ({ product: i.product?.id || i.id, quantity: i.quantity || 1 })),
        ...(appliedCoupons.length > 0 ? { coupon_codes: appliedCoupons.map(c => c.code) } : {}),
        ...(useCredit && creditApplied > 0 ? { use_store_credit: Math.floor(creditApplied) } : {}),
        ...(fingerprint ? { fingerprint } : {}),
      })
      useCartStore.getState().clearCart()
      client.delete('/api/v1/cart/clear/').catch(() => {})
      const orderId = res.data?.id || res.data?.order_id || res.data?.orders?.[0] || null
      navigate('/order-confirmed', { state: { orderId, total: finalTotal } })
    } catch (err) {
      const errCode = err.response?.data?.error
      if (errCode === 'risk_blocked') {
        setError(err.response?.data?.detail || 'Não conseguimos processar este pedido. Contacte o suporte.')
      } else {
        setError(err.response?.data?.detail || errCode || 'Erro ao processar pedido.')
      }
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

          {/* Store credit (loyalty balance) */}
          {storeCredit > 0 && (
            <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ ...S, fontSize: 13, fontWeight: 600, color: '#FFF', margin: 0 }}>
                  🪙 Usar saldo de fidelidade
                </p>
                <p style={{ ...S, fontSize: 11, color: '#9A9A9A', margin: '2px 0 0' }}>
                  Disponível: <span style={{ color: '#C9A84C', fontWeight: 600 }}>{storeCredit.toLocaleString()} Kz</span>
                  {useCredit && creditApplied > 0 && (
                    <> · A aplicar: <span style={{ color: '#059669', fontWeight: 600 }}>−{creditApplied.toLocaleString()} Kz</span></>
                  )}
                </p>
              </div>
              <div onClick={() => setUseCredit(v => !v)}
                style={{ width: 44, height: 24, borderRadius: 12, background: useCredit ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0 }}>
                <div style={{ position: 'absolute', top: 3, left: useCredit ? 23 : 3, width: 18, height: 18, borderRadius: '50%', background: '#FFF', transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }} />
              </div>
            </div>
          )}

          {/* Promo code */}
          <div>
            <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>🎟️ Códigos promocionais</h2>
            <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 12 }}>Pode combinar 1 cupão da plataforma + 1 cupão de cada loja.</p>

            {/* Applied coupons list */}
            {appliedCoupons.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                {appliedCoupons.map(c => (
                  <div key={c.code} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(5,150,105,0.08)', border: '1px solid rgba(5,150,105,0.25)', borderRadius: 10, padding: '8px 12px' }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#FFF', margin: 0 }}>
                        {c.code}
                        <span style={{ ...S, fontSize: 10, color: '#9A9A9A', fontWeight: 400, marginLeft: 6 }}>
                          {c.scope === 'platform' ? 'Plataforma' : (c.seller_name ? `Loja ${c.seller_name}` : 'Loja')}
                        </span>
                      </p>
                    </div>
                    <span style={{ ...S, fontSize: 13, fontWeight: 700, color: '#059669' }}>−{fmt(c.discount_amount)}</span>
                    <button onClick={() => removeCoupon(c.code)} style={{ background: 'none', border: 'none', color: '#9A9A9A', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0 }}>×</button>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={couponCode}
                onChange={e => { setCouponCode(e.target.value.toUpperCase()); setCouponError('') }}
                onKeyDown={e => { if (e.key === 'Enter') handleApplyCoupon() }}
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
            {couponError && (
              <p style={{ ...S, fontSize: 12, color: '#ef4444', marginTop: 6 }}>{couponError}</p>
            )}
          </div>

          {/* Updated total with discount */}
          {discountAmount > 0 && (
            <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Subtotal</span>
                <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>{fmt(total)}</span>
              </div>
              {appliedCoupons.map(c => (
                <div key={c.code} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ ...S, fontSize: 13, color: '#059669' }}>Desconto ({c.code})</span>
                  <span style={{ ...S, fontSize: 13, color: '#059669' }}>−{fmt(c.discount_amount)}</span>
                </div>
              ))}
              {creditApplied > 0 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ ...S, fontSize: 13, color: '#059669' }}>🪙 Saldo de fidelidade</span>
                  <span style={{ ...S, fontSize: 13, color: '#059669' }}>−{fmt(creditApplied)}</span>
                </div>
              )}
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
