import client from '@/api/client'
import api from '@/api/client'
/**
 * MICHA Express — Buyer Checkout UX
 * Covers improvements: 17 (Multicaixa UI), 18 (Order summary), 
 * 19 (Saved addresses), 20 (Promo code feedback), 21 (Progress bar)
 */
import { useState } from 'react'
import { asList } from '@/lib/asList'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

const fmt = (n) => n.toLocaleString('pt-AO') + ' Kz'

// ─── Checkout Progress Bar ──────────────────────────────────────────────────
export function CheckoutProgressBar({ step }) {
  const steps = ['Endereço', 'Pagamento', 'Revisão', 'Confirmado']
  return (
    <div style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: 0 }}>
      {steps.map((label, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>
          {/* Connector line */}
          {i > 0 && (
            <div style={{
              position: 'absolute', left: '-50%', top: 10, width: '100%', height: 2,
              background: i <= step ? GOLD : BORDER,
              transition: 'background 0.3s'
            }} />
          )}
          {/* Circle */}
          <div style={{
            width: 20, height: 20, borderRadius: '50%', zIndex: 1,
            background: i < step ? GOLD : i === step ? GOLD : CARD,
            border: `2px solid ${i <= step ? GOLD : BORDER}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.3s'
          }}>
            {i < step && (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="3" strokeLinecap="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </div>
          <span style={{
            fontFamily: "'DM Sans', sans-serif", fontSize: 10, marginTop: 4,
            color: i <= step ? GOLD : MUTED, fontWeight: i === step ? 600 : 400
          }}>{label}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Saved Addresses ────────────────────────────────────────────────────────
export function SavedAddresses({ selected, onSelect }) {
  const [addresses, setAddresses] = useState([
    { id: 1, label: 'Casa', name: 'António Cabaço', street: 'Rua dos Jacarandás 42', neighbourhood: 'Talatona', city: 'Luanda', phone: '+244 923 456 789' },
    { id: 2, label: 'Trabalho', name: 'António Cabaço', street: 'Av. 4 de Fevereiro 120', neighbourhood: 'Ingombota', city: 'Luanda', phone: '+244 923 456 789' },
  ])
  useEffect(() => {
    client.get('/api/v1/shipping/addresses/').then(res => {
      const data = asList(res.data)
      if (data.length > 0) setAddresses(data.map(a => ({
        id: a.id, label: a.label || 'Casa',
        name: a.recipient_name || '', street: a.street || '',
        neighbourhood: a.neighbourhood || '', city: a.city || '',
        phone: a.phone || '',
      })))
    }).catch(() => {})
  }, [])
  const [adding, setAdding] = useState(false)

  return (
    <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Endereço de entrega
      </h3>
      {addresses.map(addr => (
        <button key={addr.id} onClick={() => onSelect(addr)} style={{
          background: selected?.id === addr.id ? 'rgba(201,168,76,0.08)' : CARD,
          border: `1.5px solid ${selected?.id === addr.id ? GOLD : BORDER}`,
          borderRadius: 14, padding: 14, cursor: 'pointer', textAlign: 'left', transition: 'all 0.2s'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{
              fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600,
              color: selected?.id === addr.id ? GOLD : MUTED,
              background: selected?.id === addr.id ? 'rgba(201,168,76,0.15)' : 'rgba(255,255,255,0.05)',
              padding: '2px 8px', borderRadius: 4
            }}>{addr.label}</span>
            <div style={{
              width: 18, height: 18, borderRadius: '50%',
              border: `2px solid ${selected?.id === addr.id ? GOLD : BORDER}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              {selected?.id === addr.id && <div style={{ width: 8, height: 8, borderRadius: '50%', background: GOLD }} />}
            </div>
          </div>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: TEXT, fontWeight: 500, margin: 0 }}>{addr.name}</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '2px 0 0' }}>
            {addr.street}, {addr.neighbourhood}, {addr.city}
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '2px 0 0' }}>{addr.phone}</p>
        </button>
      ))}
      <button onClick={() => setAdding(true)} style={{
        background: 'none', border: `1.5px dashed ${BORDER}`, borderRadius: 14,
        padding: 14, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="2" strokeLinecap="round">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED }}>Adicionar novo endereço</span>
      </button>
    </div>
  )
}

// ─── Promo Code Input ───────────────────────────────────────────────────────
export function PromoCodeInput({ onApply }) {
  const [code, setCode] = useState('')
  const [state, setState] = useState('idle') // idle | loading | success | error
  const [discount, setDiscount] = useState(0)
  const [shake, setShake] = useState(false)

  const handleApply = async () => {
    if (!code.trim()) return
    setState('loading')
    // Simulate API call
    try {
      const res = await api.post('/api/v1/promotions/coupons/validate/', { code })
      const data = res.data
      setState('success')
      setDiscount(data.discount_value || 10)
      onApply && onApply(data.discount_value || 10)
      return
    } catch {
      setState('error')
      setShake(true)
      setTimeout(() => setShake(false), 500)
      setTimeout(() => setState('idle'), 2000)
      return
    }
    if (false) {
      setState('success')
      setDiscount(10)
      onApply && onApply(10)
    } else {
      setState('error')
      setShake(true)
      setTimeout(() => setShake(false), 500)
      setTimeout(() => setState('idle'), 2000)
    }
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center',
        animation: shake ? 'shake 0.4s ease' : 'none'
      }}>
        <style>{`@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}`}</style>
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            value={code}
            onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="Código promocional"
            style={{
              width: '100%', padding: '12px 14px',
              background: state === 'success' ? 'rgba(5,150,105,0.08)' : state === 'error' ? 'rgba(239,68,68,0.08)' : CARD,
              border: `1.5px solid ${state === 'success' ? '#059669' : state === 'error' ? '#EF4444' : BORDER}`,
              borderRadius: 12, color: TEXT, fontFamily: "'DM Sans', sans-serif",
              fontSize: 14, letterSpacing: '0.05em', outline: 'none', boxSizing: 'border-box',
              transition: 'all 0.2s'
            }}
          />
          {state === 'success' && (
            <div style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
          )}
        </div>
        <button onClick={handleApply} disabled={state === 'loading' || state === 'success'} style={{
          padding: '12px 16px', borderRadius: 12, border: 'none', cursor: 'pointer',
          background: state === 'success' ? '#059669' : GOLD,
          color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600,
          opacity: state === 'loading' ? 0.7 : 1, transition: 'all 0.2s', whiteSpace: 'nowrap'
        }}>
          {state === 'loading' ? '...' : state === 'success' ? 'Aplicado!' : 'Aplicar'}
        </button>
      </div>
      {state === 'success' && (
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669', marginTop: 6 }}>
          Desconto de {discount}% aplicado com sucesso
        </p>
      )}
      {state === 'error' && (
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#EF4444', marginTop: 6 }}>
          Código inválido ou expirado
        </p>
      )}
    </div>
  )
}

// ─── Order Summary ───────────────────────────────────────────────────────────
export function OrderSummary({ items = [], discount = 0 }) {
  const subtotal = items.reduce((s, i) => s + i.price * i.qty, 0)
  const delivery = subtotal > 50000 ? 0 : 1500
  const discountAmt = subtotal * (discount / 100)
  const total = subtotal + delivery - discountAmt

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}` }}>
          <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
            Resumo do pedido
          </h3>
        </div>
        <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Row label="Subtotal" value={fmt(subtotal)} />
          <Row label="Entrega" value={delivery === 0 ? 'Grátis' : fmt(delivery)} valueColor={delivery === 0 ? '#059669' : TEXT} />
          {discount > 0 && <Row label={`Desconto (${discount}%)`} value={`-${fmt(discountAmt)}`} valueColor="#059669" />}
          <div style={{ height: 1, background: BORDER, margin: '4px 0' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: TEXT }}>Total</span>
            <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: GOLD }}>{fmt(total)}</span>
          </div>
          {delivery === 0 && subtotal > 0 && (
            <div style={{ background: 'rgba(5,150,105,0.08)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 8, padding: '8px 10px' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#059669', margin: 0 }}>
                Entrega grátis para compras acima de 50.000 Kz
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, valueColor = TEXT }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED }}>{label}</span>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: valueColor, fontWeight: 500 }}>{value}</span>
    </div>
  )
}

// ─── Multicaixa Payment UI ──────────────────────────────────────────────────
export function MulticaixaPaymentUI({ reference, amount, expiresAt }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(reference)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ background: CARD, borderRadius: 16, border: `1.5px solid ${GOLD}`, overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '16px', background: 'rgba(201,168,76,0.08)', borderBottom: `1px solid rgba(201,168,76,0.2)`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: GOLD, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="2" strokeLinecap="round">
              <rect x="2" y="5" width="20" height="14" rx="2" /><line x1="2" y1="10" x2="22" y2="10" />
            </svg>
          </div>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: GOLD, margin: 0 }}>Multicaixa Express</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>Pague via ATM ou app</p>
          </div>
        </div>

        {/* Reference */}
        <div style={{ padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Referência de pagamento
            </p>
            <div style={{
              fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700,
              color: TEXT, letterSpacing: '0.15em',
              background: '#0A0A0A', padding: '16px 20px', borderRadius: 12,
              border: `1px solid ${BORDER}`, userSelect: 'all'
            }}>
              {reference || '123 456 789'}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', background: '#0A0A0A', borderRadius: 10, padding: '10px 14px' }}>
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '0 0 2px', textTransform: 'uppercase' }}>Valor</p>
              <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: GOLD, margin: 0 }}>{fmt(amount || 0)}</p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '0 0 2px', textTransform: 'uppercase' }}>Expira em</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#EF4444', margin: 0 }}>
                {expiresAt || '23:45:00'}
              </p>
            </div>
          </div>

          <button onClick={copy} style={{
            width: '100%', padding: '14px', borderRadius: 12, border: 'none', cursor: 'pointer',
            background: copied ? 'rgba(5,150,105,0.2)' : 'rgba(201,168,76,0.15)',
            color: copied ? '#059669' : GOLD,
            fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            transition: 'all 0.2s'
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              {copied
                ? <polyline points="20 6 9 17 4 12" />
                : <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>
              }
            </svg>
            {copied ? 'Referência copiada!' : 'Copiar referência'}
          </button>

          <div style={{ background: 'rgba(201,168,76,0.05)', borderRadius: 10, padding: '12px' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0, lineHeight: 1.6 }}>
              Aceda ao seu banco ou app Multicaixa Express e seleccione{' '}
              <strong style={{ color: TEXT }}>Pagamentos → Referência</strong>. Introduza a referência acima e confirme o pagamento.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Demo Page ──────────────────────────────────────────────────────────────
export default function CheckoutUXDemo() {
  const [step, setStep] = useState(1)
  const [selectedAddr, setSelectedAddr] = useState(null)
  const [discount, setDiscount] = useState(0)

  const items = [
    { id: 1, name: 'Samsung Galaxy S24', price: 180000, qty: 1 },
    { id: 2, name: 'Capinha protectora', price: 5000, qty: 2 },
  ]

  return (
    <div style={{ background: BG, minHeight: '100vh', paddingBottom: 40 }}>
      <div style={{ maxWidth: 420, margin: '0 auto' }}>
        <div style={{ padding: '40px 0 0', textAlign: 'center' }}>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, color: TEXT, margin: '0 0 4px' }}>Checkout</h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED }}>Buyer UX improvements demo</p>
        </div>

        <CheckoutProgressBar step={step} />

        <div style={{ display: 'flex', gap: 8, padding: '0 16px 20px', justifyContent: 'center' }}>
          {[0,1,2,3].map(s => (
            <button key={s} onClick={() => setStep(s)} style={{
              padding: '6px 12px', borderRadius: 8, border: `1px solid ${step === s ? GOLD : BORDER}`,
              background: step === s ? 'rgba(201,168,76,0.1)' : 'none',
              color: step === s ? GOLD : MUTED, cursor: 'pointer',
              fontFamily: "'DM Sans', sans-serif", fontSize: 12
            }}>Step {s}</button>
          ))}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SavedAddresses selected={selectedAddr} onSelect={setSelectedAddr} />
          <PromoCodeInput onApply={setDiscount} />
          <OrderSummary items={items} discount={discount} />
          <MulticaixaPaymentUI reference="847 293 015" amount={185500} expiresAt="23:45:00" />
        </div>
      </div>
    </div>
  )
}
