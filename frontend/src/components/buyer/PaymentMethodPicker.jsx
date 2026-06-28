import { useState, useEffect } from 'react'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * PaymentMethodPicker — AliExpress Complete 2025 CH 12.
 *
 * Renders every payment method the spec lists, gated by the
 * country the buyer is checking out in. Each method has:
 *   • A card with logo, name, and a one-liner sub-text.
 *   • A click handler that POSTs to /api/v1/payments/initiate/
 *     with {method, order_id, amount}. The backend returns either
 *     a real provider redirect URL/QR (when wired) or a stub
 *     payload (when not). Either way, every selection is logged
 *     to UserEvent so the checkout funnel is measurable.
 *
 * Why stubs not real SDKs
 * ───────────────────────
 * Stripe Elements / PayPal Buttons / Klarna SDK / Apple Pay JS API
 * each require merchant credentials we don't have. The selector +
 * downstream UI is fully shipped here so swapping in the real SDK
 * is a one-component edit per method (e.g. drop the PayPalButtons
 * component into the PayPal card's onClick handler).
 *
 * Props:
 *   country      — ISO-2, drives method availability
 *   amount       — currency-major (e.g. 99.99) for "Pay X" labels
 *   currency     — 'AOA' | 'USD' | 'EUR' (display only)
 *   onSelect(m)  — called with the method key when user picks one
 *
 * Methods supported (from spec §12.1):
 *   card · alipay · paypal · googlepay · applepay · klarna ·
 *   afterpay · multicaixa · unitel_money · wallet · cod · bank_wire
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const METHODS = [
  { key: 'card',         logo: '💳', name: 'Cartão de crédito/débito', sub: 'Visa, Mastercard, UnionPay · 3D Secure', countries: '*' },
  { key: 'multicaixa',   logo: '🏧', name: 'Multicaixa Express',       sub: 'QR ou número Multicaixa',         countries: ['AO'] },
  { key: 'unitel_money', logo: '📱', name: 'Unitel Money',              sub: 'Carteira móvel angolana',          countries: ['AO'] },
  { key: 'wallet',       logo: '👛', name: 'MICHA Wallet',              sub: 'Saldo instantâneo',                countries: '*' },
  { key: 'cod',          logo: '💵', name: 'Pagamento na entrega',     sub: 'Disponível em cidades suportadas', countries: ['AO'] },
  { key: 'bank_wire',    logo: '🏦', name: 'Transferência bancária',   sub: 'Referência ATM',                   countries: ['AO', 'PT'] },
  { key: 'paypal',       logo: '🅿️', name: 'PayPal',                   sub: 'Dupla protecção AliExpress + PayPal', countries: ['US', 'GB', 'PT', 'BR', 'ES', 'FR', 'DE'] },
  { key: 'googlepay',    logo: '🟢', name: 'Google Pay',                 sub: 'Toque · biometria',                countries: ['US', 'GB', 'PT', 'ES', 'FR', 'DE', 'BR'] },
  { key: 'applepay',     logo: '🍎', name: 'Apple Pay',                  sub: 'Face ID / Touch ID',               countries: ['US', 'GB', 'PT', 'ES', 'FR', 'DE'] },
  { key: 'klarna',       logo: '🅺', name: 'Klarna — Pague em 3x',       sub: 'Sem juros · check rápido',         countries: ['US', 'GB', 'DE', 'SE'] },
  { key: 'afterpay',     logo: 'AP', name: 'Afterpay — Pague em 4x',     sub: '4 prestações quinzenais',         countries: ['US', 'GB', 'AU', 'CA'] },
  { key: 'alipay',       logo: '🇨🇳', name: 'Alipay',                  sub: 'QR · login Alipay',                countries: ['CN', 'HK', 'TW', 'MO'] },
]

export default function PaymentMethodPicker({ country = 'AO', amount = 0, currency = 'AOA', onSelect, orderId = null }) {
  const [picked, setPicked] = useState(null)
  const [methods, setMethods] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const cc = (country || 'AO').toUpperCase()
    const filtered = METHODS.filter(m => m.countries === '*' || m.countries.includes(cc))
    setMethods(filtered)
    track('checkout.payment_methods_shown', { country: cc, count: filtered.length })
  }, [country])

  const pick = async (m) => {
    setPicked(m.key)
    track('checkout.payment_method_selected', { method: m.key, country, amount })
    onSelect?.(m.key)
  }

  const pay = async () => {
    if (!picked) return
    setBusy(true)
    try {
      const res = await client.post('/api/v1/payments/initiate/', {
        method: picked, order_id: orderId, amount, currency,
      })
      track('checkout.payment_initiated', { method: picked, status: res.data?.status })
      // Each method has a tailored redirect/QR flow. We log + best-effort open.
      const url = res.data?.redirect_url
      if (url) {
        track('checkout.payment_redirect', { method: picked, url: url.slice(0, 80) })
        window.location.href = url
      } else if (res.data?.qr_code_url) {
        // Open a modal with the QR — handled by parent. We just emit.
        onSelect?.(picked, res.data)
      } else if (res.data?.reference) {
        alert(`Referência: ${res.data.reference}\nMontante: ${amount} ${currency}`)
      } else {
        alert('Pagamento iniciado.')
      }
    } catch (e) {
      track('checkout.payment_failed', { method: picked, error: e.response?.data?.detail || '' })
      alert(e.response?.data?.detail || 'Falha ao iniciar pagamento.')
    } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {methods.map(m => {
        const isPicked = picked === m.key
        return (
          <button key={m.key} type="button" onClick={() => pick(m)}
            style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 14,
              background: isPicked ? 'rgba(201,168,76,0.1)' : '#141414',
              border: `1.5px solid ${isPicked ? '#C9A84C' : '#1E1E1E'}`,
              borderRadius: 14, cursor: 'pointer', textAlign: 'left',
            }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#0F0F0F', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{m.logo}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ ...S, fontSize: 13, color: '#FFF', fontWeight: 600 }}>{m.name}</p>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{m.sub}</p>
            </div>
            <div style={{ width: 18, height: 18, borderRadius: '50%', border: `2px solid ${isPicked ? '#C9A84C' : '#2A2A2A'}`, background: isPicked ? '#C9A84C' : 'transparent', flexShrink: 0 }} />
          </button>
        )
      })}
      {picked && orderId && (
        <button onClick={pay} disabled={busy}
          style={{ marginTop: 8, padding: '14px 0', borderRadius: 12, border: 'none', background: busy ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: busy ? 'wait' : 'pointer' }}>
          {busy ? 'A iniciar pagamento…' : `Pagar ${amount} ${currency}`}
        </button>
      )}
    </div>
  )
}
