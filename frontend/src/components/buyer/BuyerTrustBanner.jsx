/**
 * BuyerTrustBanner — inline trust badges for PDP and checkout.
 *
 * NOTE: distinct from <BuyerProtectionBanner> which is the order-page
 * "your order is protected until delivery" timer banner. This component
 * is the pre-purchase trust signal — visible above the fold on PDPs
 * and on the checkout summary to reduce trust-driven cart abandonment.
 *
 * Three signals
 * ─────────────
 *   1. "Comprador Protegido" — every paid order is held in escrow
 *      until delivery
 *   2. "Devolução em 14 dias" — return window
 *   3. "Pagamento Seguro" — encrypted PSP flow
 *
 * Variants
 * ────────
 *   default — full banner with hints, used on PDPs
 *   compact — single row of pills, used in checkout summary
 */


const ITEMS = [
  {
    icon: '🛡️',
    label: 'Comprador Protegido',
    hint: 'Reembolso garantido se não receberes',
  },
  {
    icon: '↩️',
    label: 'Devolução 14 dias',
    hint: 'Sem questões',
  },
  {
    icon: '🔒',
    label: 'Pagamento Seguro',
    hint: 'Encriptado fim-a-fim',
  },
]


export default function BuyerTrustBanner({ compact = false }) {
  if (compact) {
    return (
      <div
        role="region"
        aria-label="Garantias MICHA"
        style={{
          display: 'flex', gap: 12, padding: '10px 12px',
          background: 'rgba(34, 197, 94, 0.08)',
          border: '1px solid rgba(34, 197, 94, 0.18)',
          borderRadius: 10, alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        {ITEMS.map((i) => (
          <span key={i.label} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 12, color: '#86EFAC', fontWeight: 500,
          }}>
            <span aria-hidden="true">{i.icon}</span>
            {i.label}
          </span>
        ))}
      </div>
    )
  }

  return (
    <div
      role="region"
      aria-label="Garantias MICHA"
      style={{
        margin: '12px 16px',
        padding: 14,
        background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.08) 0%, rgba(34, 197, 94, 0.03) 100%)',
        border: '1px solid rgba(34, 197, 94, 0.18)',
        borderRadius: 12,
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
      }}>
        <span aria-hidden="true" style={{ fontSize: 20 }}>🛡️</span>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#86EFAC' }}>
          Comprador Protegido pela MICHA
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        {ITEMS.map((i) => (
          <div key={i.label} style={{ minWidth: 0 }}>
            <div style={{
              fontSize: 11, fontWeight: 600, color: '#D1FAE5',
              marginBottom: 2,
            }}>
              <span aria-hidden="true" style={{ marginRight: 4 }}>{i.icon}</span>
              {i.label}
            </div>
            <div style={{ fontSize: 10, color: '#86EFAC', opacity: 0.7 }}>
              {i.hint}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
