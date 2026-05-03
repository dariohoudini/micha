import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useCartStore as useCart } from '@/stores/cartStore'
import { useCheckout, useShippingAddresses } from '@/hooks/useQueries'
import { toast } from '@/components/ui/Toast'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'

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
        <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle" fill="white" fontSize="11" fontWeight="700" fontFamily="DM Sans">MCX</text>
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

const addressSchema = z.object({
  full_name: z.string().min(2, 'Insira o seu nome'),
  phone: z.string().min(9, 'Número inválido'),
  province: z.string().min(1),
  address: z.string().min(5, 'Insira o seu endereço'),
  reference: z.string().optional(),
})

function fmt(v) {
  return `${Number(v || 0).toLocaleString('pt-AO')} Kz`
}

function StepBar({ step }) {
  return (
    <div style={{ display: 'flex', gap: 6, marginBottom: 24 }} role="progressbar" aria-valuenow={step} aria-valuemin={1} aria-valuemax={3} aria-label={`Passo ${step} de 3`}>
      {[1, 2, 3].map(i => (
        <div key={i} style={{
          flex: 1, height: 3, borderRadius: 2,
          background: i <= step ? '#C9A84C' : '#1E1E1E',
          transition: 'background 0.3s ease',
        }} />
      ))}
    </div>
  )
}

export default function CheckoutPage() {
  const navigate = useNavigate()
  const items = useCart(s => s.items)
  const totalPrice = useCart(s => s.totalPrice)
  const clearCart = useCart(s => s.clearCart)
  const [step, setStep] = useState(1)
  const [paymentMethod, setPaymentMethod] = useState('multicaixa')
  const [selectedAddressId, setSelectedAddressId] = useState(null)

  const { data: savedAddresses = [] } = useShippingAddresses()
  const checkout = useCheckout()

  const delivery = 1500
  const total = totalPrice + delivery

  const { register, handleSubmit, reset, formState: { errors } } = useForm({
    resolver: zodResolver(addressSchema),
    defaultValues: { province: 'Luanda' },
  })

  // Pre-fill from default saved address
  useEffect(() => {
    const defaultAddr = savedAddresses.find(a => a.is_default) || savedAddresses[0]
    if (defaultAddr && !selectedAddressId) {
      setSelectedAddressId(defaultAddr.id)
      reset({
        full_name: defaultAddr.full_name || '',
        phone: defaultAddr.phone || '',
        province: defaultAddr.province || 'Luanda',
        address: defaultAddr.address || '',
        reference: defaultAddr.reference || '',
      })
    }
  }, [savedAddresses])

  const onAddressSubmit = () => setStep(2)

  const handlePlaceOrder = async () => {
    checkout.mutate(
      {
        items: items.map(i => ({ product: i.id, quantity: i.quantity })),
        payment_method: paymentMethod,
        delivery_province: 'Luanda',
      },
      {
        onSuccess: (res) => {
          clearCart()
          navigate('/order-confirmed', {
            state: { orderId: res.data?.id || res.data?.order_id },
          })
        },
        onError: (err) => {
          toast.error(err.response?.data?.detail || 'Erro ao processar pedido. Tente novamente.')
        },
      }
    )
  }

  const stepTitles = ['Entrega', 'Pagamento', 'Confirmação']

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      {/* Header */}
      <header style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <button
            onClick={() => step > 1 ? setStep(s => s - 1) : navigate('/cart')}
            aria-label="Voltar"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#FFFFFF' }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
              {stepTitles[step - 1]}
            </h1>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>
              Passo {step} de 3
            </p>
          </div>
        </div>
        <StepBar step={step} />
      </header>

      <main id="main-content" className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Step 1 — Delivery */}
          {step === 1 && (
            <form onSubmit={handleSubmit(onAddressSubmit)} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Saved addresses selector */}
              {savedAddresses.length > 0 && (
                <div>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 10 }}>
                    Endereços guardados
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                    {savedAddresses.map(addr => (
                      <button
                        key={addr.id}
                        type="button"
                        onClick={() => {
                          setSelectedAddressId(addr.id)
                          reset({
                            full_name: addr.full_name || '',
                            phone: addr.phone || '',
                            province: addr.province || 'Luanda',
                            address: addr.address || '',
                            reference: addr.reference || '',
                          })
                        }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 12,
                          padding: '12px 14px', borderRadius: 12, textAlign: 'left',
                          background: selectedAddressId === addr.id ? 'rgba(201,168,76,0.08)' : '#141414',
                          border: `1.5px solid ${selectedAddressId === addr.id ? '#C9A84C' : '#1E1E1E'}`,
                          cursor: 'pointer', transition: 'all 0.15s',
                        }}
                      >
                        <div style={{ flex: 1 }}>
                          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF' }}>
                            {addr.full_name || addr.address}
                          </p>
                          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>
                            {addr.address}, {addr.province}
                          </p>
                        </div>
                        <div style={{
                          width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
                          border: `2px solid ${selectedAddressId === addr.id ? '#C9A84C' : '#2A2A2A'}`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          {selectedAddressId === addr.id && (
                            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#C9A84C' }} />
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                  <div style={{ height: 1, background: '#1E1E1E', marginBottom: 16 }} />
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 12 }}>
                    Ou insira um novo endereço:
                  </p>
                </div>
              )}

              <Input
                label="Nome completo"
                required
                placeholder="João Silva"
                error={errors.full_name?.message}
                {...register('full_name')}
              />

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                  Telefone <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <div style={{ display: 'flex' }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', padding: '0 14px',
                    background: '#1E1E1E', border: '1px solid #2A2A2A',
                    borderRight: 'none', borderRadius: '12px 0 0 12px',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap',
                  }}>
                    🇦🇴 +244
                  </div>
                  <input
                    className="input-base"
                    type="tel"
                    placeholder="9xx xxx xxx"
                    style={{ borderRadius: '0 12px 12px 0', flex: 1 }}
                    {...register('phone')}
                  />
                </div>
                {errors.phone && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#ef4444' }} role="alert">{errors.phone.message}</p>}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                  Província
                </label>
                <select className="input-base" {...register('province')}>
                  {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>

              <Input
                label="Endereço completo"
                required
                placeholder="Rua, bairro, número…"
                error={errors.address?.message}
                {...register('address')}
              />

              <Input
                label="Ponto de referência"
                optional
                placeholder="Ex: Próximo ao Belas Shopping"
                error={errors.reference?.message}
                {...register('reference')}
              />

              <Button type="submit" variant="primary" size="full" style={{ marginTop: 8 }}>
                Continuar
              </Button>
            </form>
          )}

          {/* Step 2 — Payment */}
          {step === 2 && (
            <>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>
                Selecione o método de pagamento
              </p>

              {PAYMENT_METHODS.map(method => (
                <button
                  key={method.id}
                  onClick={() => setPaymentMethod(method.id)}
                  aria-pressed={paymentMethod === method.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 16, padding: '16px',
                    borderRadius: 16, cursor: 'pointer', textAlign: 'left', width: '100%',
                    background: paymentMethod === method.id ? 'rgba(201,168,76,0.08)' : '#141414',
                    border: `1.5px solid ${paymentMethod === method.id ? '#C9A84C' : '#2A2A2A'}`,
                    transition: 'all 0.2s',
                  }}
                >
                  {method.icon}
                  <div style={{ flex: 1 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: paymentMethod === method.id ? '#C9A84C' : '#FFFFFF' }}>
                      {method.label}
                    </p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>
                      {method.sub}
                    </p>
                  </div>
                  <div style={{
                    width: 20, height: 20, borderRadius: '50%',
                    border: `2px solid ${paymentMethod === method.id ? '#C9A84C' : '#2A2A2A'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    {paymentMethod === method.id && (
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#C9A84C' }} />
                    )}
                  </div>
                </button>
              ))}

              {/* Order summary */}
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #2A2A2A', padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Subtotal</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>{fmt(totalPrice)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Entrega</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>{fmt(delivery)}</span>
                </div>
                <div style={{ height: 1, background: '#2A2A2A', marginBottom: 12 }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{fmt(total)}</span>
                </div>
              </div>

              <Button variant="primary" size="full" onClick={() => setStep(3)}>
                Continuar
              </Button>
            </>
          )}

          {/* Step 3 — Confirm */}
          {step === 3 && (
            <>
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #2A2A2A', padding: 16 }}>
                <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Produtos ({items.length})
                </h3>
                {items.map(item => (
                  <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{
                      fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF',
                      flex: 1, marginRight: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {item.name} ×{item.quantity}
                    </span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#C9A84C', flexShrink: 0 }}>
                      {fmt(item.price * item.quantity)}
                    </span>
                  </div>
                ))}
                <div style={{ height: 1, background: '#2A2A2A', margin: '12px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Total</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{fmt(total)}</span>
                </div>
              </div>

              <Button
                variant="primary"
                size="full"
                loading={checkout.isPending}
                onClick={handlePlaceOrder}
              >
                Confirmar Pedido · {fmt(total)}
              </Button>

              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', textAlign: 'center', lineHeight: 1.5 }}>
                Ao confirmar aceita os nossos Termos de Uso e Política de Devoluções
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
