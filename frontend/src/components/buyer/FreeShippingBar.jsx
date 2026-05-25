/**
 * FreeShippingBar — progress bar showing how close the buyer is to
 * free shipping.
 *
 * Classic conversion lever for marketplaces: a buyer 800 Kz away
 * from free shipping is ~3x more likely to add another item than
 * one with no signal. AO 4G users see this and add items they were
 * already considering — net basket size up.
 *
 * Props
 * ─────
 *   subtotal           current cart subtotal (Kz)
 *   freeShippingAt     threshold (Kz). Defaults to 30000 — change
 *                      per merchant policy / via settings.
 *
 * a11y: role="progressbar" with aria-valuenow/min/max + readable label.
 */
const DEFAULT_FREE_SHIPPING_AT = 30000


function fmt(n) {
  return Number(n || 0).toLocaleString('pt-AO') + ' Kz'
}


export default function FreeShippingBar({
  subtotal,
  freeShippingAt = DEFAULT_FREE_SHIPPING_AT,
}) {
  const cur = Math.max(0, Number(subtotal) || 0)
  const target = Math.max(1, Number(freeShippingAt) || DEFAULT_FREE_SHIPPING_AT)
  const remaining = Math.max(0, target - cur)
  const achieved = remaining === 0
  const pct = Math.min(100, Math.round((cur / target) * 100))

  return (
    <div
      role="progressbar"
      aria-valuenow={cur}
      aria-valuemin={0}
      aria-valuemax={target}
      aria-label={
        achieved
          ? 'Frete grátis desbloqueado'
          : `Faltam ${fmt(remaining)} para frete grátis`
      }
      style={{
        padding: '12px 14px',
        background: achieved
          ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.12) 0%, rgba(34, 197, 94, 0.05) 100%)'
          : 'rgba(201, 168, 76, 0.06)',
        border: `1px solid ${achieved ? 'rgba(34, 197, 94, 0.3)' : 'rgba(201, 168, 76, 0.25)'}`,
        borderRadius: 12,
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginBottom: 8,
      }}>
        <span aria-hidden="true" style={{ fontSize: 18 }}>
          {achieved ? '🎉' : '🚚'}
        </span>
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 13, fontWeight: 600,
          color: achieved ? '#4ADE80' : '#FBBF24',
          margin: 0, lineHeight: 1.3, flex: 1,
        }}>
          {achieved
            ? 'Frete grátis desbloqueado!'
            : <>Faltam <strong>{fmt(remaining)}</strong> para frete grátis</>}
        </p>
      </div>

      {/* Track */}
      <div
        aria-hidden="true"
        style={{
          width: '100%', height: 6, borderRadius: 999,
          background: 'rgba(255, 255, 255, 0.06)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`, height: '100%',
            background: achieved
              ? 'linear-gradient(90deg, #4ADE80 0%, #22C55E 100%)'
              : 'linear-gradient(90deg, #C9A84C 0%, #FBBF24 100%)',
            borderRadius: 999,
            transition: 'width 240ms ease',
          }}
        />
      </div>
    </div>
  )
}
