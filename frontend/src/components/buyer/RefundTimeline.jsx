/**
 * RefundTimeline — AliExpress Complete 2025 CH 14.3.
 *
 * Static info card listing per-method refund timelines. Surfaced on
 * the Order Detail screen and the Dispute / Return submission flow
 * so buyers know what to expect.
 *
 * Props:
 *   method   — current order's payment method key (matches the
 *              PaymentMethodPicker keys); highlights the matching row.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const TIMELINES = [
  { k: 'card',         label: 'Cartão',            eta: '3-7 dias úteis' },
  { k: 'paypal',       label: 'PayPal',             eta: 'Até 24h' },
  { k: 'alipay',       label: 'Alipay',             eta: 'Até 24h (frequentemente no mesmo dia)' },
  { k: 'wallet',       label: 'MICHA Wallet',       eta: 'Imediato' },
  { k: 'klarna',       label: 'Klarna',             eta: 'Ajusta prestações restantes' },
  { k: 'bank_wire',    label: 'Transferência',     eta: '5-15 dias úteis' },
  { k: 'multicaixa',   label: 'Multicaixa Express', eta: 'Até 24h' },
  { k: 'unitel_money', label: 'Unitel Money',      eta: 'Até 24h' },
  { k: 'googlepay',    label: 'Google Pay',         eta: '3-7 dias (depende do cartão)' },
  { k: 'applepay',     label: 'Apple Pay',          eta: '3-7 dias (depende do cartão)' },
  { k: 'cod',          label: 'Pagamento na entrega', eta: 'Crédito em wallet (instantâneo)' },
]

export default function RefundTimeline({ method }) {
  return (
    <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, padding: 14 }}>
      <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Prazos de reembolso</p>
      {TIMELINES.map(t => {
        const active = t.k === method
        return (
          <div key={t.k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #1E1E1E' }}>
            <span style={{ ...S, fontSize: 12, color: active ? '#C9A84C' : '#BFBFBF', fontWeight: active ? 700 : 400 }}>
              {active ? '› ' : ''}{t.label}
            </span>
            <span style={{ ...S, fontSize: 11, color: active ? '#C9A84C' : '#9A9A9A' }}>{t.eta}</span>
          </div>
        )
      })}
      <p style={{ ...S, fontSize: 10, color: '#555', marginTop: 8, lineHeight: 1.4 }}>
        Prazos indicativos. Disputas com prova clara são resolvidas em 48h.
      </p>
    </div>
  )
}
