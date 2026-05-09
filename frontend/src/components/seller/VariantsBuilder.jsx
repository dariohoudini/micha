import { useEffect, useMemo } from 'react'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#2A2A2A'
const RED = '#dc2626'
const S = { fontFamily: "'DM Sans', sans-serif" }

const inputStyle = {
  background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10,
  padding: '10px 12px', ...S, fontSize: 13, color: TEXT, outline: 'none',
  boxSizing: 'border-box',
}

const SUGGESTED_AXES = ['Cor', 'Tamanho', 'Material']

function cartesian(arrays) {
  return arrays.reduce(
    (acc, arr) => acc.flatMap(a => arr.map(b => [...a, b])),
    [[]],
  )
}

function comboKey(options) {
  return Object.entries(options)
    .map(([k, v]) => `${k}:${v}`)
    .sort()
    .join('|')
}

/**
 * Variant builder for sellers.
 *
 * Props:
 *   axes: [{ name: "Cor", values: ["Vermelho", "Azul"] }]
 *   combos: [{ options, price, quantity, sku }]
 *   defaultPrice: fallback price for new combos
 *   defaultStock: fallback stock for new combos
 *   onChange: (axes, combos) => void
 */
export default function VariantsBuilder({ axes = [], combos = [], defaultPrice = '', defaultStock = '', onChange }) {
  // Auto-regenerate combos when axes/values change. Preserve price/stock for existing keys.
  const computedCombos = useMemo(() => {
    if (!axes.length || axes.some(a => !a.name || !a.values?.length)) return []
    const valueArrays = axes.map(a => a.values)
    const product = cartesian(valueArrays)
    const existing = new Map(combos.map(c => [comboKey(c.options || {}), c]))
    return product.map(combo => {
      const options = {}
      axes.forEach((a, i) => { options[a.name] = combo[i] })
      const key = comboKey(options)
      const prior = existing.get(key)
      return {
        options,
        price: prior?.price ?? defaultPrice ?? '',
        quantity: prior?.quantity ?? defaultStock ?? '0',
        sku: prior?.sku ?? '',
      }
    })
  }, [axes, defaultPrice, defaultStock]) // intentionally not depending on combos

  // Re-emit combos when axes change so parent stays in sync
  useEffect(() => {
    if (axes.length && computedCombos.length) {
      const sameLength = combos.length === computedCombos.length
      const sameKeys = sameLength && combos.every((c, i) =>
        comboKey(c.options || {}) === comboKey(computedCombos[i].options || {})
      )
      if (!sameKeys) onChange?.(axes, computedCombos)
    } else if (!axes.length && combos.length) {
      onChange?.(axes, [])
    }
  }, [axes, computedCombos]) // eslint-disable-line

  const updateAxis = (idx, patch) => {
    const next = axes.map((a, i) => i === idx ? { ...a, ...patch } : a)
    onChange?.(next, combos)
  }

  const addAxis = () => {
    if (axes.length >= 3) return
    const used = axes.map(a => a.name)
    const suggested = SUGGESTED_AXES.find(s => !used.includes(s)) || ''
    onChange?.([...axes, { name: suggested, values: [] }], combos)
  }

  const removeAxis = (idx) => {
    const next = axes.filter((_, i) => i !== idx)
    onChange?.(next, combos)
  }

  const addValue = (idx, raw) => {
    const value = raw.trim()
    if (!value) return
    const axis = axes[idx]
    if (axis.values.includes(value)) return
    updateAxis(idx, { values: [...axis.values, value] })
  }

  const removeValue = (idx, value) => {
    const axis = axes[idx]
    updateAxis(idx, { values: axis.values.filter(v => v !== value) })
  }

  const updateCombo = (idx, patch) => {
    const next = combos.map((c, i) => i === idx ? { ...c, ...patch } : c)
    onChange?.(axes, next)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Axis editor */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {axes.map((axis, axisIdx) => (
          <div key={axisIdx} style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, padding: 12 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <input
                value={axis.name}
                onChange={e => updateAxis(axisIdx, { name: e.target.value })}
                placeholder="Nome (ex: Cor, Tamanho)"
                style={{ ...inputStyle, flex: 1 }}
              />
              <button
                type="button"
                onClick={() => removeAxis(axisIdx)}
                style={{ background: 'transparent', border: `1px solid ${RED}`, borderRadius: 10, padding: '0 12px', color: RED, ...S, fontSize: 12, cursor: 'pointer' }}
              >
                Remover
              </button>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
              {axis.values.map(v => (
                <span key={v} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(201,168,76,0.1)', border: `1px solid ${GOLD}`, borderRadius: 8, padding: '4px 10px', ...S, fontSize: 12, color: GOLD }}>
                  {v}
                  <button
                    type="button"
                    onClick={() => removeValue(axisIdx, v)}
                    style={{ background: 'none', border: 'none', color: GOLD, cursor: 'pointer', padding: 0, fontSize: 14, lineHeight: 1 }}
                  >×</button>
                </span>
              ))}
            </div>

            <ValueInput onAdd={(v) => addValue(axisIdx, v)} />
          </div>
        ))}

        {axes.length < 3 && (
          <button
            type="button"
            onClick={addAxis}
            style={{ background: 'transparent', border: `1px dashed ${BORDER}`, borderRadius: 12, padding: '12px 14px', color: GOLD, ...S, fontSize: 13, fontWeight: 500, cursor: 'pointer' }}
          >
            + Adicionar opção {axes.length === 0 ? '(Cor, Tamanho, etc.)' : ''}
          </button>
        )}
      </div>

      {/* Combo grid */}
      {combos.length > 0 && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ padding: '10px 12px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ ...S, fontSize: 12, fontWeight: 600, color: TEXT }}>{combos.length} variante{combos.length !== 1 ? 's' : ''}</span>
            <button
              type="button"
              onClick={() => onChange?.(axes, combos.map(c => ({ ...c, price: defaultPrice, quantity: defaultStock })))}
              style={{ background: 'none', border: 'none', color: GOLD, ...S, fontSize: 11, cursor: 'pointer' }}
            >
              Aplicar preço/stock padrão a todos
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {combos.map((combo, i) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 0.6fr', gap: 8, padding: '10px 12px', borderTop: i === 0 ? 'none' : `1px solid ${BORDER}` }}>
                <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                  <p style={{ ...S, fontSize: 12, color: TEXT, margin: 0 }}>
                    {Object.values(combo.options).join(' / ')}
                  </p>
                  <p style={{ ...S, fontSize: 10, color: MUTED, margin: 0, marginTop: 2 }}>
                    {Object.entries(combo.options).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                  </p>
                </div>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Preço (Kz)"
                  value={combo.price}
                  onChange={e => updateCombo(i, { price: e.target.value })}
                  style={{ ...inputStyle, fontSize: 12 }}
                />
                <input
                  type="number"
                  min="0"
                  placeholder="Stock"
                  value={combo.quantity}
                  onChange={e => updateCombo(i, { quantity: e.target.value })}
                  style={{ ...inputStyle, fontSize: 12 }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ValueInput({ onAdd }) {
  const handleKey = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      onAdd(e.currentTarget.value)
      e.currentTarget.value = ''
    }
  }
  const handleBlur = (e) => {
    if (e.currentTarget.value.trim()) {
      onAdd(e.currentTarget.value)
      e.currentTarget.value = ''
    }
  }
  return (
    <input
      placeholder="Escrever valor e Enter (ex: Vermelho, Azul...)"
      onKeyDown={handleKey}
      onBlur={handleBlur}
      style={{ ...inputStyle, width: '100%' }}
    />
  )
}
