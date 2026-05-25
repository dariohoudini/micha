/**
 * BrandProtectedBadge — small pill shown on listings that match an
 * entry in the R4 ProtectedBrand registry.
 *
 * Why it exists
 * ─────────────
 * Counterfeits are ~30% of African e-commerce reports. The R4
 * brand-protection registry (apps/moderation/brand_registry.py) flags
 * any listing using a registered brand name → routes them to a
 * higher-priority moderator queue. Buyers benefit only if they can
 * SEE that signal — this badge surfaces it.
 *
 * "Marca verificada" reads ambiguously without context, so the tooltip
 * carries the precise meaning: "Esta marca está registada na MICHA.
 * Vendedores não-autorizados são bloqueados na criação da listagem."
 *
 * Two render modes:
 *   default — inline pill (used on PDP, store header)
 *   icon   — compact icon-only with title (used on dense product cards)
 *
 * Props
 * ─────
 *   brand          string — brand name; absence = no render
 *   onPress        opens brand verification info modal
 *   icon (bool)    icon-only mode
 */


export default function BrandProtectedBadge({
  brand,
  onPress,
  icon = false,
}) {
  if (!brand) return null

  const description = `${brand}: marca verificada pelo registo MICHA`

  if (icon) {
    return (
      <span
        role="img"
        aria-label={description}
        title={description}
        style={{
          display: 'inline-flex', alignItems: 'center',
          justifyContent: 'center',
          width: 18, height: 18,
          background: 'rgba(59, 130, 246, 0.15)',
          border: '1px solid rgba(59, 130, 246, 0.4)',
          borderRadius: 6, fontSize: 10,
          color: '#3B82F6', fontWeight: 700,
          fontFamily: "'DM Sans', sans-serif",
        }}
      >
        ✓
      </span>
    )
  }

  return (
    <button
      type="button"
      onClick={onPress}
      aria-label={description}
      title={description}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '4px 10px', borderRadius: 999,
        background: 'rgba(59, 130, 246, 0.1)',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        color: '#60A5FA',
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 11, fontWeight: 600,
        cursor: onPress ? 'pointer' : 'default',
        lineHeight: 1,
      }}
    >
      <span aria-hidden="true">🛡️</span>
      Marca verificada
    </button>
  )
}
