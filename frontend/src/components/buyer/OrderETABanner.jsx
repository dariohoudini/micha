/**
 * OrderETABanner — prominent ETA display for active orders.
 *
 * Why
 * ───
 * Pre-fix: OrderDetailPage shows a list of statuses + timestamps. The
 * single piece of information buyers actually scan for — "when does
 * it arrive?" — is buried in the timeline.
 *
 * This banner answers that question above the fold, in pt-AO. Disappears
 * on terminal states (delivered, cancelled, refunded).
 *
 * Props
 * ─────
 *   status                 order status string
 *   estimatedDeliveryAt    ISO datetime; preferred
 *   protectionDeadlineAt   fallback when ETA unavailable (shows urgency
 *                          for awaiting_seller / awaiting_ship)
 *   shippedAt              fallback for "shipped" — show "Chega em ~2 dias"
 *                          based on average AO carrier window
 *
 * Display rules
 * ─────────────
 *   pending / awaiting_seller   "Aguarda confirmação do vendedor"
 *   confirmed / awaiting_ship   "A ser preparado"
 *   shipped                      "Chega em X dias úteis"  (ETA-derived)
 *   delivered                    hidden
 *   cancelled / refunded         hidden
 */


function formatDayWord(date) {
  const dayNames = ['domingo', 'segunda', 'terça', 'quarta',
                    'quinta', 'sexta', 'sábado']
  return dayNames[date.getDay()]
}


function daysUntil(target) {
  const now = new Date()
  const t = new Date(target)
  if (isNaN(t.getTime())) return null
  const ms = t.getTime() - now.getTime()
  return Math.max(0, Math.ceil(ms / 86_400_000))
}


function etaCopy({ status, estimatedDeliveryAt, shippedAt }) {
  if (status === 'shipped' || status === 'in_transit') {
    if (estimatedDeliveryAt) {
      const d = daysUntil(estimatedDeliveryAt)
      if (d === 0) return { headline: 'Chega hoje', sub: 'O teu pedido está a caminho.' }
      if (d === 1) return { headline: 'Chega amanhã', sub: 'O teu pedido está a caminho.' }
      const dt = new Date(estimatedDeliveryAt)
      return {
        headline: `Chega ${formatDayWord(dt)}`,
        sub: `Estimativa: ${dt.toLocaleDateString('pt-AO', { day: '2-digit', month: 'short' })}`,
      }
    }
    if (shippedAt) {
      // Conservative AO default: 3-5 days from shipped.
      const shipped = new Date(shippedAt)
      const minD = new Date(shipped); minD.setDate(minD.getDate() + 3)
      const maxD = new Date(shipped); maxD.setDate(maxD.getDate() + 5)
      return {
        headline: 'A caminho',
        sub: `Estimativa: ${minD.toLocaleDateString('pt-AO', { day: '2-digit', month: 'short' })}–${maxD.toLocaleDateString('pt-AO', { day: '2-digit', month: 'short' })}`,
      }
    }
    return { headline: 'A caminho', sub: 'Estimativa em breve.' }
  }

  if (status === 'confirmed' || status === 'awaiting_ship' || status === 'processing') {
    return {
      headline: 'A ser preparado',
      sub: 'O vendedor está a embalar o teu pedido.',
    }
  }

  if (status === 'pending' || status === 'awaiting_seller') {
    return {
      headline: 'Aguarda confirmação do vendedor',
      sub: 'O vendedor tem 48h para confirmar o pedido.',
    }
  }

  return null
}


const TERMINAL = new Set(['delivered', 'completed', 'cancelled', 'refunded', 'returned'])


export default function OrderETABanner({
  status,
  estimatedDeliveryAt,
  shippedAt,
  protectionDeadlineAt,
}) {
  if (!status || TERMINAL.has(status)) return null
  const copy = etaCopy({ status, estimatedDeliveryAt, shippedAt })
  if (!copy) return null

  const isShipped = status === 'shipped' || status === 'in_transit'
  const accent = isShipped ? '#4ADE80' : '#FBBF24'
  const accentBg = isShipped ? 'rgba(34, 197, 94, 0.08)' : 'rgba(245, 158, 11, 0.08)'
  const accentBorder = isShipped ? 'rgba(34, 197, 94, 0.25)' : 'rgba(245, 158, 11, 0.25)'

  return (
    <div
      role="region"
      aria-label="Previsão de entrega"
      style={{
        padding: '14px 16px',
        background: accentBg,
        border: `1px solid ${accentBorder}`,
        borderRadius: 14,
        fontFamily: "'DM Sans', sans-serif",
        display: 'flex', alignItems: 'center', gap: 12,
      }}
    >
      <div aria-hidden="true" style={{
        fontSize: 24, lineHeight: 1,
      }}>
        {isShipped ? '🚚' : status === 'pending' || status === 'awaiting_seller' ? '⏳' : '📦'}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 15, fontWeight: 700, color: accent,
          marginBottom: 2, lineHeight: 1.3,
        }}>
          {copy.headline}
        </div>
        <div style={{
          fontSize: 12, color: '#9A9A9A', lineHeight: 1.4,
        }}>
          {copy.sub}
        </div>
      </div>
    </div>
  )
}
