const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#2A2A2A'
const RED = '#dc2626'
const GREEN = '#059669'
const S = { fontFamily: "'DM Sans', sans-serif" }

const inputStyle = {
  background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10,
  padding: '10px 12px', ...S, fontSize: 13, color: TEXT, outline: 'none',
  boxSizing: 'border-box',
}

/**
 * Bulk pricing tiers builder.
 *
 * Props:
 *   tiers: [{ min_quantity, unit_price }]  (id optional)
 *   basePrice: string|number — the product's regular unit price (used for % savings hint)
 *   onChange: (nextTiers) => void
 */
export default function PriceTiersBuilder({ tiers = [], basePrice = '', onChange }) {
  const updateTier = (idx, patch) => {
    onChange?.(tiers.map((t, i) => i === idx ? { ...t, ...patch } : t))
  }
  const removeTier = (idx) => {
    onChange?.(tiers.filter((_, i) => i !== idx))
  }
  const addTier = () => {
    if (tiers.length >= 4) return
    // Suggest next min_quantity = max existing + 5 (or 5 for first)
    const maxQ = tiers.reduce((m, t) => Math.max(m, Number(t.min_quantity) || 0), 1)
    const nextQ = maxQ === 1 ? 5 : maxQ + 5
    onChange?.([...tiers, { min_quantity: nextQ, unit_price: '' }])
  }

  const base = Number(basePrice) || 0
  const sorted = [...tiers].sort((a, b) => Number(a.min_quantity) - Number(b.min_quantity))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <p style={{ ...S, fontSize: 11, color: MUTED, margin: 0 }}>
        Oferece descontos por quantidade. Compradores que comprem ≥ N unidades pagam o preço da escala.
      </p>

      {sorted.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {sorted.map((t, i) => {
            const minQ = Number(t.min_quantity) || 0
            const unitPrice = Number(t.unit_price) || 0
            const savings = base > 0 && unitPrice > 0 && unitPrice < base
              ? Math.round((1 - unitPrice / base) * 100)
              : null
            const tooHigh = base > 0 && unitPrice >= base

            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: 2 }}>
                    <label style={{ ...S, fontSize: 10, color: MUTED }}>A partir de</label>
                    <input
                      type="number"
                      min="2"
                      value={t.min_quantity}
                      onChange={e => updateTier(tiers.indexOf(t), { min_quantity: e.target.value })}
                      placeholder="5"
                      style={{ ...inputStyle, fontSize: 13 }}
                    />
                  </div>
                  <span style={{ ...S, fontSize: 11, color: MUTED, marginTop: 16 }}>un por</span>
                  <div style={{ display: 'flex', flexDirection: 'column', flex: 1.4, gap: 2 }}>
                    <label style={{ ...S, fontSize: 10, color: MUTED }}>Preço unitário</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={t.unit_price}
                      onChange={e => updateTier(tiers.indexOf(t), { unit_price: e.target.value })}
                      placeholder="2800"
                      style={{ ...inputStyle, fontSize: 13, borderColor: tooHigh ? 'rgba(220,38,38,0.4)' : BORDER }}
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeTier(tiers.indexOf(t))}
                  style={{ background: 'transparent', border: `1px solid ${RED}`, borderRadius: 8, color: RED, cursor: 'pointer', padding: '8px 10px', marginTop: 16, ...S, fontSize: 12 }}>
                  ×
                </button>
                {savings && (
                  <span style={{ position: 'absolute', marginLeft: -100, marginTop: 32, ...S, fontSize: 10, color: GREEN, fontWeight: 600 }}>
                    −{savings}%
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {tiers.length < 4 && (
        <button
          type="button"
          onClick={addTier}
          style={{
            background: 'transparent', border: `1px dashed ${BORDER}`, borderRadius: 12,
            padding: '11px 14px', color: GOLD, ...S, fontSize: 13, fontWeight: 500, cursor: 'pointer',
          }}>
          + Adicionar escala de preço
        </button>
      )}
    </div>
  )
}
