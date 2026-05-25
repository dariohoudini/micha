/**
 * SellerTrustChip — visual badge for SellerTrustScore (R4).
 *
 * Maps backend badge_level → visible chip with the right colour +
 * icon. Used inline on ProductCard, on PDP seller mini-card, and
 * on the store page header.
 *
 * Variants by SellerTrustScore.badge_level:
 *   elite     gold       "Vendedor de Elite"
 *   trusted   silver     "Vendedor de Confiança"
 *   good      bronze     "Bom Vendedor"
 *   verified  blue       "Vendedor Verificado"
 *   new       grey       "Em avaliação" (hidden by default)
 *
 * Three sizes:
 *   xs   inline next to a name (10px font, no label, icon-only with title attr)
 *   sm   below name on cards (default)
 *   md   above the fold on PDP / store header
 *
 * Compact prop hides the label, showing only icon + colour. Useful on
 * small product cards in dense grids.
 *
 * a11y: each chip has aria-label + title attribute with the full label.
 */


const BADGES = {
  elite: {
    color: '#C9A84C', icon: '⭐',
    label: 'Vendedor de Elite',
    short: 'Elite',
  },
  trusted: {
    color: '#A1A1AA', icon: '✓',
    label: 'Vendedor de Confiança',
    short: 'Confiança',
  },
  good: {
    color: '#CD7F32', icon: '◐',
    label: 'Bom Vendedor',
    short: 'Bom',
  },
  verified: {
    color: '#3B82F6', icon: '✓',
    label: 'Vendedor Verificado',
    short: 'Verificado',
  },
  new: {
    color: '#71717A', icon: '◯',
    label: 'Em avaliação',
    short: 'Novo',
  },
}


export default function SellerTrustChip({
  level,
  size = 'sm',
  compact = false,
  // Allow a custom on-click — e.g. show score breakdown modal.
  onPress,
}) {
  // 'new' is hidden by default — no public-facing seller starts displaying
  // a low badge before they have data. Backend keeps score_is_public=false
  // until min_orders_for_public; this is a UI belt-and-suspenders.
  if (!level || level === 'new') return null

  const badge = BADGES[level]
  if (!badge) return null

  const dimensions = {
    xs: { fontSize: 9,  padX: 4, padY: 1, iconSize: 9,  gap: 2 },
    sm: { fontSize: 10, padX: 6, padY: 2, iconSize: 10, gap: 4 },
    md: { fontSize: 12, padX: 10, padY: 4, iconSize: 12, gap: 6 },
  }[size] || { fontSize: 10, padX: 6, padY: 2, iconSize: 10, gap: 4 }

  return (
    <span
      role={onPress ? 'button' : 'img'}
      tabIndex={onPress ? 0 : undefined}
      onClick={onPress}
      onKeyDown={(e) => {
        if (onPress && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onPress()
        }
      }}
      aria-label={badge.label}
      title={badge.label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: dimensions.gap,
        padding: `${dimensions.padY}px ${dimensions.padX}px`,
        background: `${badge.color}1A`,
        border: `1px solid ${badge.color}40`,
        borderRadius: 999,
        fontSize: dimensions.fontSize,
        fontWeight: 600,
        color: badge.color,
        fontFamily: "'DM Sans', sans-serif",
        whiteSpace: 'nowrap',
        cursor: onPress ? 'pointer' : 'default',
        lineHeight: 1,
      }}
    >
      <span aria-hidden="true" style={{ fontSize: dimensions.iconSize }}>
        {badge.icon}
      </span>
      {!compact && (size === 'md' ? badge.label : badge.short)}
    </span>
  )
}
