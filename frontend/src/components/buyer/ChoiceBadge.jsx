/**
 * ChoiceBadge / LocalWarehouseBadge — AliExpress Complete 2025 CH 8.
 *
 * Two tiny presentational components for the "trust signal" badges
 * that should appear on product cards across the buyer app:
 *
 *   <ChoiceBadge />              — orange "choice" pill, shown when
 *                                  product.is_choice === true.
 *   <LocalWarehouseBadge country="AO" />
 *                                — country-flag pill, shown when
 *                                  product.ships_from_country is set.
 *
 * The product API may not yet populate these fields. The badges are
 * defensive: they render nothing if their input is falsy. This means
 * dropping them into any product card is safe today and they'll
 * start appearing automatically once the backend ships the fields.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const FLAGS = {
  AO: '🇦🇴', PT: '🇵🇹', BR: '🇧🇷', CN: '🇨🇳', US: '🇺🇸', GB: '🇬🇧',
  ES: '🇪🇸', FR: '🇫🇷', DE: '🇩🇪', IT: '🇮🇹', ZA: '🇿🇦', NG: '🇳🇬',
}
const NAMES = {
  AO: 'Angola', PT: 'Portugal', BR: 'Brasil', CN: 'China', US: 'EUA', GB: 'Reino Unido',
  ES: 'Espanha', FR: 'França', DE: 'Alemanha', IT: 'Itália', ZA: 'África do Sul', NG: 'Nigéria',
}

export function ChoiceBadge() {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 7px', borderRadius: 4,
      background: '#C9A84C', color: '#0A0A0A',
      ...S, fontSize: 9, fontWeight: 800, letterSpacing: '0.04em',
      textTransform: 'lowercase',
    }}>
      ✦ choice
    </span>
  )
}

export function LocalWarehouseBadge({ country }) {
  if (!country) return null
  const c = String(country).toUpperCase().slice(0, 2)
  const flag = FLAGS[c] || '🌍'
  const label = NAMES[c] || country
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 7px', borderRadius: 4,
      background: 'rgba(255,255,255,0.08)', color: '#FFFFFF',
      ...S, fontSize: 9, fontWeight: 600,
      border: '1px solid rgba(255,255,255,0.12)',
    }}>
      {flag} {label}
    </span>
  )
}

/** Convenience: render Choice if true, else Local if set, else nothing. */
export default function TrustBadge({ product }) {
  if (!product) return null
  if (product.is_choice) return <ChoiceBadge />
  if (product.ships_from_country) return <LocalWarehouseBadge country={product.ships_from_country} />
  return null
}
