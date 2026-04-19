import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCartStore as useCart } from '@/stores/cartStore'
import { formatPrice } from '@/components/buyer/mockData'

const PROVINCES = [
  'Luanda', 'Benguela', 'Huambo', 'Bié', 'Malanje',
  'Huíla', 'Cabinda', 'Uíge', 'Cunene', 'Namibe',
  'Moxico', 'Cuando Cubango', 'Lunda Norte', 'Lunda Sul',
  'Kwanza Norte', 'Kwanza Sul', 'Bengo', 'Zaire',
]

const PAYMENT_METHODS = [
  {
    id: 'multicaixa',
    label: 'Multicaixa Express',
    sub: 'Pagamento via referência Multicaixa',
    icon: (
      <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
        <rect width="40" height="40" rx="8" fill="#E30613" />
        <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
          fill="white" fontSize="11" fontWeight="700" fontFamily="DM Sans">MCX</text>
      </svg>
    ),
  },
  {
    id: 'cash',
    label: 'Pagamento na Entrega',
    sub: 'Pague em dinheiro ao receber',
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <circle cx="12" cy="12" r="3" />
        <path d="M6 12h.01M18 12h.01" />
      </svg>
    ),
  },
]

export default function CheckoutPage() {
  const navigate = useNavigate()
  const items = useCart(s => s.items); const totalPrice = useCart(s => s.totalPrice); const clearCart = useCart(s => s.clearCart)
  const [step, setStep] = useState(1) // 1: address, 2: payment, 3: confirm
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    full_name: '', phone: '', province: 'Luanda',
    address: '', reference: '', payment_method: 'multicaixa',
  })

  const delivery = items.some(i => i.express) ? 0 : 1500
  const total = totalPrice + delivery

  const handleChange = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }))

  const validateStep1 = () => {
    if (!form.full_name.trim()) return 'Insira o seu nome completo.'
    if (!form.phone.trim()) return 'Insira o seu número de telefone.'
    if (!form.address.trim()) return 'Insira o seu endereço.'
    return null
  }

  const handlePlaceOrder = async () => {
    setLoading(true)
    // TODO: call ordersAPI.checkout(form) when backend is ready
    await new Promise(r => setTimeout(r, 1500))
    clearCart()
    navigate('/order-confirmed', { state: { orderId: 'ORD-' + Math.random().toString(36).slice(2, 8).toUpperCase() } })
  }

  const Label = ({ children }) => (
    <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
      {children}
    </label>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      {/* Header */}
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : navigate('/cart')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
              {step === 1 ? 'Entrega' : step === 2 ? 'Pagamento' : 'Confirmação'}
            </h1>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>Passo {step} de 3</p>
          </div>
        </div>

        {/* Progress */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 24 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{
              flex: 1, height: 3, borderRadius: 2,
              background: i <= step ? '#C9A84C' : '#1E1E1E',
              transition: 'background 0.3s ease',
            }} />
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Step 1 — Delivery address */}
          {step === 1 && (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Nome completo</Label>
                <input className="input-base" name="full_name" placeholder="João Silva"
                  value={form.full_name} onChange={handleChange} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Telefone</Label>
                <div style={{ display: 'flex' }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', padding: '0 14px',
                    background: '#1E1E1E', border: '1px solid #2A2A2A',
                    borderRight: 'none', borderRadius: '12px 0 0 12px',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 14,
                    color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap',
                  }}>🇦🇴 +244</div>
                  <input className="input-base" name="phone" type="tel"
                    placeholder="9xx xxx xxx" value={form.phone} onChange={handleChange}
                    style={{ borderRadius: '0 12px 12px 0', flex: 1 }} />
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Província</Label>
                <select className="input-base" name="province" value={form.province} onChange={handleChange}
                  style={{ appearance: 'none', cursor: 'pointer' }}>
                  {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Endereço completo</Label>
                <input className="input-base" name="address"
                  placeholder="Rua, bairro, número..." value={form.address} onChange={handleChange} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Ponto de referência <span style={{ color: '#555' }}>(opcional)</span></Label>
                <input className="input-base" name="reference"
                  placeholder="Ex: Próximo ao Belas Shopping" value={form.reference} onChange={handleChange} />
              </div>

              <button className="btn-primary" style={{ marginTop: 8 }}
                onClick={() => {
                  const err = validateStep1()
                  if (err) { alert(err); return }
                  setStep(2)
                }}>
                Continuar
              </button>
            </>
          )}

          {/* Step 2 — Payment */}
          {step === 2 && (
            <>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>
                Selecione o método de pagamento
              </p>

              {PAYMENT_METHODS.map(method => (
                <button key={method.id}
                  onClick={() => setForm(f => ({ ...f, payment_method: method.id }))}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 16,
                    padding: '16px 16px', borderRadius: 16, cursor: 'pointer', textAlign: 'left',
                    background: form.payment_method === method.id ? 'rgba(201,168,76,0.08)' : '#141414',
                    border: `1.5px solid ${form.payment_method === method.id ? '#C9A84C' : '#2A2A2A'}`,
                    transition: 'all 0.2s',
                  }}>
                  {method.icon}
                  <div style={{ flex: 1 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: form.payment_method === method.id ? '#C9A84C' : '#FFFFFF' }}>
                      {method.label}
                    </p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>
                      {method.sub}
                    </p>
                  </div>
                  <div style={{
                    width: 20, height: 20, borderRadius: '50%',
                    border: `2px solid ${form.payment_method === method.id ? '#C9A84C' : '#2A2A2A'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {form.payment_method === method.id && (
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#C9A84C' }} />
                    )}
                  </div>
                </button>
              ))}

              {/* Order summary mini */}
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #2A2A2A', padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Subtotal</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>{formatPrice(totalPrice)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Entrega</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: delivery === 0 ? '#059669' : '#FFFFFF' }}>{delivery === 0 ? 'Grátis' : formatPrice(delivery)}</span>
                </div>
                <div style={{ height: 1, background: '#2A2A2A', marginBottom: 12 }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(total)}</span>
                </div>
              </div>

              <button className="btn-primary" onClick={() => setStep(3)}>
                Continuar
              </button>
            </>
          )}

          {/* Step 3 — Confirm */}
          {step === 3 && (
            <>
              {/* Delivery summary */}
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #2A2A2A', padding: 16 }}>
                <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Entrega</h3>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF', fontWeight: 500 }}>{form.full_name}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: 4 }}>+244 {form.phone}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: 2 }}>{form.address}, {form.province}</p>
                {form.reference && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>{form.reference}</p>}
              </div>

              {/* Items summary */}
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #2A2A2A', padding: 16 }}>
                <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Produtos ({items.length})</h3>
                {items.map(item => (
                  <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', flex: 1, marginRight: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.name} ×{item.quantity}
                    </span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#C9A84C', flexShrink: 0 }}>{formatPrice(item.price * item.quantity)}</span>
                  </div>
                ))}
                <div style={{ height: 1, background: '#2A2A2A', margin: '12px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(total)}</span>
                </div>
              </div>

              <button className="btn-primary"
                onClick={handlePlaceOrder} disabled={loading}
                style={{ opacity: loading ? 0.7 : 1 }}>
                {loading ? 'A processar...' : `Confirmar Pedido · ${formatPrice(total)}`}
              </button>

              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', textAlign: 'center', lineHeight: 1.5 }}>
                Ao confirmar aceita os nossos Termos de Uso e Política de Devoluções
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
