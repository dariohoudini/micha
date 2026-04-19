import { useState } from 'react'

const RATINGS = [4, 3, 2, 1]

export default function FilterDrawer({ visible, onClose, onApply }) {
  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')
  const [minRating, setMinRating] = useState(null)
  const [expressOnly, setExpressOnly] = useState(false)

  const handleApply = () => {
    onApply({ priceMin: Number(priceMin) || 0, priceMax: Number(priceMax) || Infinity, minRating, expressOnly })
    onClose()
  }

  const handleReset = () => {
    setPriceMin(''); setPriceMax(''); setMinRating(null); setExpressOnly(false)
  }

  if (!visible) return null

  return (
    <>
      {/* Backdrop */}
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 50 }} />

      {/* Drawer */}
      <div style={{
        position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
        width: '100%', maxWidth: 430, zIndex: 51,
        background: '#141414', borderRadius: '20px 20px 0 0',
        border: '1px solid #2A2A2A', borderBottom: 'none',
        padding: '0 20px 40px',
      }}>
        {/* Handle */}
        <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A', margin: '12px auto 20px' }} />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Filtros</h2>
          <button onClick={handleReset} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>Limpar</button>
        </div>

        {/* Price range */}
        <div style={{ marginBottom: 24 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 12 }}>Intervalo de preço (Kz)</p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input className="input-base" type="number" placeholder="Mín" value={priceMin} onChange={e => setPriceMin(e.target.value)} style={{ flex: 1 }} />
            <span style={{ color: '#9A9A9A', fontFamily: "'DM Sans', sans-serif" }}>—</span>
            <input className="input-base" type="number" placeholder="Máx" value={priceMax} onChange={e => setPriceMax(e.target.value)} style={{ flex: 1 }} />
          </div>
        </div>

        {/* Rating */}
        <div style={{ marginBottom: 24 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 12 }}>Avaliação mínima</p>
          <div style={{ display: 'flex', gap: 8 }}>
            {RATINGS.map(r => (
              <button key={r} onClick={() => setMinRating(minRating === r ? null : r)}
                style={{
                  flex: 1, padding: '8px 0', borderRadius: 10, cursor: 'pointer',
                  border: `1.5px solid ${minRating === r ? '#C9A84C' : '#2A2A2A'}`,
                  background: minRating === r ? 'rgba(201,168,76,0.1)' : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3,
                }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill={minRating === r ? '#C9A84C' : '#9A9A9A'}>
                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                </svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: minRating === r ? '#C9A84C' : '#9A9A9A' }}>{r}+</span>
              </button>
            ))}
          </div>
        </div>

        {/* Express only toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28, background: '#1E1E1E', borderRadius: 14, border: '1px solid #2A2A2A', padding: '14px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#C9A84C"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }}>Apenas Express</span>
          </div>
          <div onClick={() => setExpressOnly(v => !v)}
            style={{ width: 44, height: 24, borderRadius: 12, background: expressOnly ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer', transition: 'background 0.2s' }}>
            <div style={{ position: 'absolute', top: 3, left: expressOnly ? 23 : 3, width: 18, height: 18, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }} />
          </div>
        </div>

        <button className="btn-primary" onClick={handleApply}>Aplicar filtros</button>
      </div>
    </>
  )
}
