/**
 * FilterSheet — bottom-sheet filter UI for product browsing (F11).
 *
 * What changed vs inline ExplorePage version
 * ───────────────────────────────────────────
 *  • Real focus trap — Tab / Shift-Tab cycle inside the sheet
 *  • ESC closes; backdrop click closes
 *  • Focus restored to the element that opened the sheet
 *  • Sticky bottom CTA — primary "Apply" button stays visible while
 *    long filter lists scroll
 *  • Sticky top header — "Filtros" title + close button always visible
 *  • body-scroll-lock while open (prevents the page underneath
 *    scrolling on iOS)
 *  • role="dialog" + aria-modal + aria-labelledby
 *  • Touch targets ≥36px throughout
 *  • Drop-in: same props shape as the previous inline version
 *
 * Props
 * ─────
 *   filters       current filter object
 *   facets        backend facet response — {brands, conditions,
 *                 price_range, discount_count, total}
 *   onChange      (newFilters) => void — fired on Apply
 *   onClose       () => void
 *   defaults      initial filter shape used by "Clear all"
 *
 * Constants the host page must provide
 * ─────────────────────────────────────
 *   PROVINCES, CONDITIONS arrays — passed in via props since they're
 *   tied to the marketplace's geographic + commerce taxonomy
 */
import { useEffect, useRef, useState } from 'react'


const S = { fontFamily: "'DM Sans', sans-serif" }


export default function FilterSheet({
  open,
  filters,
  facets,
  defaults,
  provinces = ['Todas'],
  conditions = [{ v: '', l: 'Todos' }],
  onChange,
  onClose,
}) {
  const [local, setLocal] = useState(filters)
  const previouslyFocused = useRef(null)
  const containerRef = useRef(null)
  const headerCloseRef = useRef(null)
  const applyRef = useRef(null)

  // Reset local state when sheet re-opens (consume external changes).
  useEffect(() => {
    if (open) setLocal(filters)
  }, [open, filters])

  // body-scroll-lock + focus management + ESC / Tab handling.
  useEffect(() => {
    if (!open) return

    previouslyFocused.current = document.activeElement
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Push focus into the sheet after slide-in.
    const focusTimer = setTimeout(() => {
      headerCloseRef.current?.focus()
    }, 80)

    const handleKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose?.()
        return
      }
      if (e.key !== 'Tab') return
      const container = containerRef.current
      if (!container) return
      const focusables = container.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKey)
    return () => {
      clearTimeout(focusTimer)
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = prevOverflow
      try { previouslyFocused.current?.focus?.() } catch {}
    }
  }, [open, onClose])

  if (!open) return null

  const set = (k, v) => setLocal((p) => ({ ...p, [k]: v }))
  const toggleBrand = (name) => {
    setLocal((p) => {
      const next = new Set(p.brands || [])
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return { ...p, brands: [...next] }
    })
  }
  const apply = () => { onChange?.(local); onClose?.() }
  const reset = () => setLocal(defaults || filters)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="filtersheet-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        display: 'flex', flexDirection: 'column',
        justifyContent: 'flex-end',
        background: 'rgba(0,0,0,0.6)',
        animation: 'filtersheet-fade 180ms ease',
      }}
    >
      <style>{`
        @keyframes filtersheet-fade {
          from { background: rgba(0,0,0,0); }
          to   { background: rgba(0,0,0,0.6); }
        }
        @keyframes filtersheet-slide {
          from { transform: translateY(100%); }
          to   { transform: translateY(0); }
        }
      `}</style>

      <div
        ref={containerRef}
        style={{
          background: '#0F0F0F',
          borderRadius: '20px 20px 0 0',
          border: '1px solid #1E1E1E',
          borderBottom: 'none',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          animation: 'filtersheet-slide 220ms ease-out',
        }}
      >
        {/* Grabber */}
        <div aria-hidden="true" style={{
          display: 'flex', justifyContent: 'center', padding: '12px 0',
          flexShrink: 0,
        }}>
          <div style={{
            width: 36, height: 4, borderRadius: 2, background: '#2A2A2A',
          }} />
        </div>

        {/* Sticky header */}
        <header style={{
          padding: '0 20px 12px', flexShrink: 0,
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', gap: 8,
          borderBottom: '1px solid #1E1E1E',
        }}>
          <h2 id="filtersheet-title" style={{
            ...S, fontSize: 16, fontWeight: 700, color: '#FFF',
            margin: 0,
          }}>
            Filtros
          </h2>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <button
              type="button"
              onClick={reset}
              style={{
                ...S, fontSize: 13, color: '#C9A84C',
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '8px 4px', minHeight: 36,
              }}
            >
              Limpar tudo
            </button>
            <button
              ref={headerCloseRef}
              type="button"
              onClick={onClose}
              aria-label="Fechar filtros"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 4, lineHeight: 0,
                minWidth: 36, minHeight: 36,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                   stroke="#9A9A9A" strokeWidth="2"
                   strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </header>

        {/* Scrollable body */}
        <div style={{
          flex: 1, overflowY: 'auto',
          padding: '16px 20px',
          // Pad below the sticky footer's height so the last filter
          // doesn't render under the Apply button.
          paddingBottom: 16,
        }}>
          {/* Quick toggle: discount only */}
          {facets && (
            <Section>
              <button
                type="button"
                onClick={() => set('hasDiscount', !local.hasDiscount)}
                style={{
                  display: 'flex', alignItems: 'center',
                  justifyContent: 'space-between', width: '100%',
                  padding: '12px 14px', borderRadius: 12,
                  border: `1px solid ${local.hasDiscount ? '#C9A84C' : '#2A2A2A'}`,
                  background: local.hasDiscount ? 'rgba(201,168,76,0.08)' : '#141414',
                  ...S, fontSize: 13, color: '#FFF',
                  cursor: 'pointer', minHeight: 44,
                }}
              >
                <span>
                  🔥 Apenas com desconto
                  {facets?.discount_count != null && (
                    <span style={{ color: '#9A9A9A', fontSize: 11 }}>
                      {' · '}{facets.discount_count.toLocaleString()}
                    </span>
                  )}
                </span>
                <Checkbox checked={!!local.hasDiscount} />
              </button>
            </Section>
          )}

          {/* Price range */}
          <Section>
            <Label>Intervalo de preço</Label>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <input
                value={local.minPrice}
                onChange={(e) => set('minPrice', e.target.value)}
                placeholder="Mín. Kz"
                type="number"
                inputMode="numeric"
                aria-label="Preço mínimo"
                style={inputStyle}
              />
              <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>—</span>
              <input
                value={local.maxPrice}
                onChange={(e) => set('maxPrice', e.target.value)}
                placeholder="Máx. Kz"
                type="number"
                inputMode="numeric"
                aria-label="Preço máximo"
                style={inputStyle}
              />
            </div>
            {facets?.price_range?.max > 0 && (
              <p style={{ ...S, fontSize: 11, color: '#555', marginTop: 6 }}>
                Intervalo: {facets.price_range.min.toLocaleString()} – {facets.price_range.max.toLocaleString()} Kz
              </p>
            )}
          </Section>

          {/* Brands */}
          {facets?.brands?.length > 0 && (
            <Section>
              <Label>
                Marca
                {local.brands?.length > 0 && (
                  <span style={{ color: '#C9A84C' }}>
                    {' · '}{local.brands.length}
                  </span>
                )}
              </Label>
              <div role="group" aria-label="Marcas"
                   style={{
                     display: 'flex', flexWrap: 'wrap', gap: 8,
                     maxHeight: 180, overflowY: 'auto',
                   }}>
                {facets.brands.map((b) => {
                  const sel = local.brands?.includes(b.name)
                  return (
                    <button
                      key={b.name}
                      type="button"
                      aria-pressed={sel}
                      onClick={() => toggleBrand(b.name)}
                      style={{
                        padding: '8px 12px', borderRadius: 20,
                        border: `1px solid ${sel ? '#C9A84C' : '#2A2A2A'}`,
                        background: sel ? 'rgba(201,168,76,0.1)' : '#141414',
                        ...S, fontSize: 12,
                        color: sel ? '#C9A84C' : '#FFF',
                        cursor: 'pointer', minHeight: 36,
                      }}
                    >
                      {b.name}{' '}
                      <span style={{ color: '#9A9A9A', fontSize: 11 }}>
                        ({b.count})
                      </span>
                    </button>
                  )
                })}
              </div>
            </Section>
          )}

          {/* Province */}
          <Section>
            <Label>Província</Label>
            <div role="radiogroup" aria-label="Província"
                 style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {provinces.map((p) => {
                const sel = local.province === p
                return (
                  <button
                    key={p}
                    type="button"
                    role="radio"
                    aria-checked={sel}
                    onClick={() => set('province', p)}
                    style={{
                      padding: '8px 14px', borderRadius: 20,
                      border: `1px solid ${sel ? '#C9A84C' : '#2A2A2A'}`,
                      background: sel ? 'rgba(201,168,76,0.1)' : '#141414',
                      ...S, fontSize: 12,
                      color: sel ? '#C9A84C' : '#9A9A9A',
                      cursor: 'pointer', minHeight: 36,
                    }}
                  >
                    {p}
                  </button>
                )
              })}
            </div>
          </Section>

          {/* Condition */}
          <Section>
            <Label>Estado</Label>
            <div role="radiogroup" aria-label="Estado"
                 style={{ display: 'flex', gap: 8 }}>
              {conditions.map((c) => {
                const sel = local.condition === c.v
                const facetCount = facets?.conditions?.find((x) => x.value === c.v)?.count
                return (
                  <button
                    key={c.v || 'all'}
                    type="button"
                    role="radio"
                    aria-checked={sel}
                    onClick={() => set('condition', c.v)}
                    style={{
                      flex: 1,
                      padding: '10px 0', borderRadius: 10,
                      border: `1px solid ${sel ? '#C9A84C' : '#2A2A2A'}`,
                      background: sel ? 'rgba(201,168,76,0.1)' : '#141414',
                      ...S, fontSize: 12,
                      color: sel ? '#C9A84C' : '#9A9A9A',
                      cursor: 'pointer', minHeight: 40,
                    }}
                  >
                    {c.l}
                    {c.v && facetCount != null && (
                      <span style={{ color: '#555', fontSize: 10, marginLeft: 4 }}>
                        ({facetCount})
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </Section>

          {/* Min rating */}
          <Section>
            <Label>Avaliação mínima</Label>
            <div role="radiogroup" aria-label="Avaliação"
                 style={{ display: 'flex', gap: 8 }}>
              {[0, 3, 4, 5].map((r) => {
                const sel = local.minRating === r
                return (
                  <button
                    key={r}
                    type="button"
                    role="radio"
                    aria-checked={sel}
                    onClick={() => set('minRating', r)}
                    style={{
                      flex: 1,
                      padding: '10px 0', borderRadius: 10,
                      border: `1px solid ${sel ? '#C9A84C' : '#2A2A2A'}`,
                      background: sel ? 'rgba(201,168,76,0.1)' : '#141414',
                      ...S, fontSize: 12,
                      color: sel ? '#C9A84C' : '#9A9A9A',
                      cursor: 'pointer', minHeight: 40,
                    }}
                  >
                    {r === 0 ? 'Todos' : `${r}★+`}
                  </button>
                )
              })}
            </div>
          </Section>
        </div>

        {/* Sticky footer with Apply CTA */}
        <footer style={{
          padding: '12px 20px max(20px, env(safe-area-inset-bottom))',
          background: '#0F0F0F',
          borderTop: '1px solid #1E1E1E',
          flexShrink: 0,
        }}>
          <button
            ref={applyRef}
            type="button"
            onClick={apply}
            style={{
              width: '100%', padding: '14px 0', borderRadius: 14,
              border: 'none', background: '#C9A84C',
              ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A',
              cursor: 'pointer', minHeight: 48,
            }}
          >
            {facets?.total != null
              ? `Mostrar ${facets.total.toLocaleString()} produtos`
              : 'Aplicar filtros'}
          </button>
        </footer>
      </div>
    </div>
  )
}


/* ─── Internals ─────────────────────────────────────────────────── */

const inputStyle = {
  flex: 1,
  background: '#141414',
  border: '1px solid #2A2A2A',
  borderRadius: 10,
  padding: '10px 12px',
  ...S, fontSize: 13, color: '#FFF', outline: 'none',
  minHeight: 40,
}

function Section({ children }) {
  return <div style={{ marginBottom: 24 }}>{children}</div>
}

function Label({ children }) {
  return (
    <p style={{
      ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A',
      marginBottom: 10, textTransform: 'uppercase',
      letterSpacing: '0.06em',
    }}>
      {children}
    </p>
  )
}

function Checkbox({ checked }) {
  return (
    <span aria-hidden="true" style={{
      width: 18, height: 18, borderRadius: 4,
      border: `1.5px solid ${checked ? '#C9A84C' : '#555'}`,
      background: checked ? '#C9A84C' : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {checked && (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
             stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </span>
  )
}
