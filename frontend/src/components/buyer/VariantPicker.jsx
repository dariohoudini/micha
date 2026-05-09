import { useMemo } from 'react'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#2A2A2A'
const S = { fontFamily: "'DM Sans', sans-serif" }

// Heuristic: treat the first axis as a swatch axis when its name implies color
const COLOR_AXIS_RE = /(cor|color|colour)/i

// Map common Portuguese color names to hex for swatches
const COLOR_MAP = {
  preto: '#0a0a0a', branco: '#fafafa', cinza: '#9a9a9a',
  vermelho: '#dc2626', rosa: '#ec4899', laranja: '#f97316',
  amarelo: '#eab308', verde: '#16a34a', azul: '#2563eb',
  roxo: '#9333ea', castanho: '#92400e', bege: '#d6b58a',
  dourado: GOLD, prateado: '#c0c0c0',
  black: '#0a0a0a', white: '#fafafa', gray: '#9a9a9a',
  red: '#dc2626', pink: '#ec4899', orange: '#f97316',
  yellow: '#eab308', green: '#16a34a', blue: '#2563eb',
  purple: '#9333ea', brown: '#92400e', beige: '#d6b58a',
  gold: GOLD, silver: '#c0c0c0',
}

function hexFor(value) {
  return COLOR_MAP[String(value).toLowerCase()] || null
}

/**
 * Generic variant picker.
 *
 * Props:
 *   axes: [{ name: "Color", values: ["Red", "Blue"] }, ...]
 *   combos: [{ id, options: {Color:"Red",Size:"M"}, price, quantity, image_url, is_active }]
 *   selectedOptions: { Color: "Red", Size: "M" }
 *   onSelect: (axisName, value) => void
 */
export default function VariantPicker({ axes = [], combos = [], selectedOptions = {}, onSelect }) {
  // For each axis value, decide if it's selectable given currently-selected other axes:
  // a value is selectable if there exists at least one in-stock active combo that matches
  // the current selection except for this axis (so user can switch within an axis freely).
  const reachable = useMemo(() => {
    const map = {}
    for (const axis of axes) {
      map[axis.name] = {}
      for (const value of axis.values) {
        const candidate = { ...selectedOptions, [axis.name]: value }
        const match = combos.find(c => {
          if (!c.is_active || c.quantity <= 0) return false
          // Must match every key in candidate that's present
          return Object.entries(candidate).every(([k, v]) => c.options?.[k] === v)
        })
        map[axis.name][value] = !!match
      }
    }
    return map
  }, [axes, combos, selectedOptions])

  if (!axes.length) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 16 }}>
      {axes.map((axis, axisIdx) => {
        const isColorAxis = COLOR_AXIS_RE.test(axis.name)
        const selected = selectedOptions[axis.name]

        return (
          <div key={axis.name}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <p style={{ ...S, fontSize: 13, fontWeight: 600, color: TEXT, margin: 0 }}>
                {axis.name}
                {selected && <span style={{ color: MUTED, fontWeight: 400, marginLeft: 8 }}>· {selected}</span>}
              </p>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {axis.values.map(value => {
                const isSelected = selected === value
                const isReachable = reachable[axis.name]?.[value]

                if (isColorAxis) {
                  // Try combo image first, then color name → hex
                  const combo = combos.find(c => c.options?.[axis.name] === value)
                  const swatchImg = combo?.image_url
                  const swatchHex = hexFor(value)

                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => onSelect?.(axis.name, value)}
                      disabled={!isReachable}
                      title={value + (isReachable ? '' : ' (esgotado)')}
                      style={{
                        width: 40, height: 40, borderRadius: '50%',
                        border: `2.5px solid ${isSelected ? GOLD : 'transparent'}`,
                        outline: `2px solid ${isSelected ? GOLD : 'transparent'}`,
                        outlineOffset: 2,
                        background: swatchImg ? `url(${swatchImg}) center/cover` : (swatchHex || CARD),
                        cursor: isReachable ? 'pointer' : 'not-allowed',
                        opacity: isReachable ? 1 : 0.35,
                        position: 'relative',
                        padding: 0,
                      }}
                    >
                      {!isReachable && (
                        <span style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: '#dc2626' }}>×</span>
                      )}
                    </button>
                  )
                }

                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => onSelect?.(axis.name, value)}
                    disabled={!isReachable}
                    style={{
                      minWidth: 44, height: 44, padding: '0 14px', borderRadius: 10,
                      border: `1.5px solid ${isSelected ? GOLD : BORDER}`,
                      background: isSelected ? 'rgba(201,168,76,0.1)' : CARD,
                      ...S,
                      fontSize: 13,
                      fontWeight: isSelected ? 600 : 400,
                      color: !isReachable ? MUTED : (isSelected ? GOLD : TEXT),
                      cursor: isReachable ? 'pointer' : 'not-allowed',
                      opacity: isReachable ? 1 : 0.55,
                      textDecoration: !isReachable ? 'line-through' : 'none',
                    }}
                  >
                    {value}
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * Helper: given product.variant_combos and current selectedOptions,
 * find the matching combo (or null if selection is incomplete/invalid).
 */
export function findMatchingCombo(combos, selectedOptions) {
  if (!combos?.length) return null
  return combos.find(c =>
    c.is_active &&
    Object.entries(selectedOptions).every(([k, v]) => c.options?.[k] === v) &&
    Object.keys(c.options || {}).every(k => selectedOptions[k] !== undefined)
  ) || null
}
