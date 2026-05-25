/**
 * ActiveFilterPills — visual chips for currently-applied filters.
 *
 * Renders a horizontally-scrollable row of removable chips above the
 * product results. Each chip has an "×" affordance to clear that one
 * filter. A "Limpar tudo" chip at the end clears everything.
 *
 * Designed to be a pure presentational component: the parent decides
 * the filter shape + onRemove semantics. No localStorage, no fetches.
 *
 * Props
 * ─────
 *   filters      filter object — shape decided by parent
 *   onRemove     (key, value?) => void
 *   onClearAll   () => void
 *
 * a11y
 * ─────
 *   role="list" + role="listitem" on chips
 *   aria-label on each remove button describes what it removes
 */


const S = { fontFamily: "'DM Sans', sans-serif" }


function chipsFromFilters(filters) {
  if (!filters) return []
  const chips = []
  if (filters.minPrice || filters.maxPrice) {
    const label = filters.minPrice && filters.maxPrice
      ? `${formatPrice(filters.minPrice)}–${formatPrice(filters.maxPrice)}`
      : filters.minPrice
        ? `Mín ${formatPrice(filters.minPrice)}`
        : `Máx ${formatPrice(filters.maxPrice)}`
    chips.push({ key: 'price', label })
  }
  if (filters.province && filters.province !== 'Todas') {
    chips.push({ key: 'province', label: filters.province })
  }
  if (filters.condition) {
    const friendly = {
      new: 'Novo', used: 'Usado', refurbished: 'Recondicionado',
    }
    chips.push({ key: 'condition', label: friendly[filters.condition] || filters.condition })
  }
  if (filters.minRating > 0) {
    chips.push({ key: 'minRating', label: `${filters.minRating}★+` })
  }
  if (filters.hasDiscount) {
    chips.push({ key: 'hasDiscount', label: '🔥 Com desconto' })
  }
  for (const b of (filters.brands || [])) {
    chips.push({ key: 'brand', value: b, label: b })
  }
  return chips
}


function formatPrice(v) {
  const n = Number(v)
  if (!n) return v
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}


export default function ActiveFilterPills({ filters, onRemove, onClearAll }) {
  const chips = chipsFromFilters(filters)
  if (chips.length === 0) return null

  return (
    <div role="list" aria-label="Filtros activos"
         style={{
           display: 'flex', gap: 6, overflowX: 'auto',
           padding: '0 16px 12px',
           // Custom scrollbar hidden on mobile.
           msOverflowStyle: 'none', scrollbarWidth: 'none',
         }}>
      <style>{`
        div[role="list"][aria-label="Filtros activos"]::-webkit-scrollbar {
          display: none;
        }
      `}</style>
      {chips.map((chip, i) => (
        <span
          key={`${chip.key}-${chip.value || chip.label}-${i}`}
          role="listitem"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 4px 6px 12px', borderRadius: 20,
            border: '1px solid rgba(201,168,76,0.3)',
            background: 'rgba(201,168,76,0.08)',
            ...S, fontSize: 11, color: '#C9A84C',
            whiteSpace: 'nowrap', flexShrink: 0,
            minHeight: 32,
          }}
        >
          {chip.label}
          <button
            type="button"
            onClick={() => onRemove?.(chip.key, chip.value)}
            aria-label={`Remover filtro: ${chip.label}`}
            style={{
              background: 'none', border: 'none', color: '#C9A84C',
              cursor: 'pointer', padding: '2px 6px',
              fontSize: 14, lineHeight: 1,
              minWidth: 24, minHeight: 24,
              display: 'flex', alignItems: 'center',
              justifyContent: 'center',
            }}
          >×</button>
        </span>
      ))}
      {chips.length > 1 && onClearAll && (
        <button
          type="button"
          onClick={onClearAll}
          style={{
            background: 'transparent', color: '#9A9A9A',
            border: '1px solid #2A2A2A',
            borderRadius: 20,
            padding: '6px 12px', cursor: 'pointer',
            ...S, fontSize: 11, fontWeight: 600,
            whiteSpace: 'nowrap', flexShrink: 0,
            minHeight: 32,
          }}
        >
          Limpar tudo
        </button>
      )}
    </div>
  )
}


/* Exported for unit tests. */
export { chipsFromFilters, formatPrice }
