/**
 * format — locale-aware number / date / currency helpers (Tier 8 i18n).
 *
 * Wraps Intl.NumberFormat / Intl.DateTimeFormat with pt-AO defaults.
 * Used across price displays, dates on orders, ETA banners, etc.
 *
 * Why centralised
 * ───────────────
 * Pre-Tier 8 the codebase had ~12 sites calling toLocaleString('pt-AO')
 * with subtly different options. Inconsistent number formatting reads
 * unprofessional ("$1,000" vs "1.000,00 Kz"). One module, one source.
 *
 * AO currency is AOA (Kwanza). Symbol: Kz. We use the suffixed
 * format ("1.000 Kz") rather than the standard Intl one to match
 * local convention.
 */


const LOCALE = 'pt-AO'


/* ─── Currency ───────────────────────────────────────────────────── */

export function formatCurrency(amount, opts = {}) {
  const n = Number(amount) || 0
  const { compact = false, withSuffix = true, currency = 'Kz' } = opts

  let body
  if (compact) {
    if (n >= 1_000_000) body = `${(n / 1_000_000).toFixed(1)}M`
    else if (n >= 1_000) body = `${Math.round(n / 1_000)}K`
    else body = formatInteger(n)
  } else {
    body = n.toLocaleString(LOCALE, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    })
  }

  return withSuffix ? `${body} ${currency}` : body
}


/* ─── Number ─────────────────────────────────────────────────────── */

export function formatInteger(n) {
  return Math.round(Number(n) || 0).toLocaleString(LOCALE)
}


export function formatDecimal(n, digits = 2) {
  return (Number(n) || 0).toLocaleString(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}


export function formatPercent(n, digits = 1) {
  return (Number(n) || 0).toLocaleString(LOCALE, {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}


/* ─── Compact short-form (5K, 1.2M) ──────────────────────────────── */

export function formatCompact(n) {
  const v = Number(n) || 0
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
  return String(v)
}


/* ─── Dates ──────────────────────────────────────────────────────── */

export function formatDate(d, opts = {}) {
  const date = toDate(d)
  if (!date) return ''
  return date.toLocaleDateString(LOCALE, {
    day: '2-digit',
    month: 'short',
    year: opts.withYear === false ? undefined : 'numeric',
  })
}


export function formatDateTime(d) {
  const date = toDate(d)
  if (!date) return ''
  return date.toLocaleString(LOCALE, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}


export function formatTimeAgo(d) {
  const date = toDate(d)
  if (!date) return ''
  const diffMs = Math.max(0, Date.now() - date.getTime())
  const secs = Math.floor(diffMs / 1000)
  if (secs < 10) return 'agora'
  if (secs < 60) return `${secs}s atrás`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}min atrás`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h atrás`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d atrás`
  if (days < 30) return `${Math.floor(days / 7)}sem atrás`
  if (days < 365) return `${Math.floor(days / 30)}m atrás`
  return `${Math.floor(days / 365)}a atrás`
}


/**
 * "Quarta, 28 Mai" — for ETA banners / delivery dates.
 */
export function formatDayLabel(d) {
  const date = toDate(d)
  if (!date) return ''
  return date.toLocaleDateString(LOCALE, {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
  })
}


function toDate(d) {
  if (!d) return null
  if (d instanceof Date) return d
  const date = new Date(d)
  return isNaN(date.getTime()) ? null : date
}


/* ─── Default export (single import alias) ──────────────────────── */

const FMT = {
  currency:   formatCurrency,
  integer:    formatInteger,
  decimal:    formatDecimal,
  percent:    formatPercent,
  compact:    formatCompact,
  date:       formatDate,
  datetime:   formatDateTime,
  timeAgo:    formatTimeAgo,
  dayLabel:   formatDayLabel,
}

export default FMT
