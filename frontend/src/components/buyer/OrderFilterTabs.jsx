import { useState } from 'react'

const GOLD = '#C9A84C'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const BG = '#0A0A0A'

const STATUS_GROUPS = {
  all: { label: 'Todos', statuses: null },
  active: { label: 'Activos', statuses: ['pending','confirmed','processing','shipped'] },
  completed: { label: 'Concluídos', statuses: ['completed','delivered'] },
  cancelled: { label: 'Cancelados', statuses: ['cancelled','refunded'] },
}

export function OrderFilterTabs({ orders, onFilter }) {
  const [active, setActive] = useState('all')

  const select = (key) => {
    setActive(key)
    const group = STATUS_GROUPS[key]
    onFilter?.(group.statuses ? orders.filter(o => group.statuses.includes(o.status)) : orders)
  }

  return (
    <div style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '0 16px 4px' }}>
      {Object.entries(STATUS_GROUPS).map(([key, { label }]) => {
        const count = key === 'all' ? orders.length : orders.filter(o => STATUS_GROUPS[key].statuses?.includes(o.status)).length
        return (
          <button key={key} onClick={() => select(key)} style={{
            padding: '7px 12px', borderRadius: 10, border: `1.5px solid ${active === key ? GOLD : BORDER}`,
            background: active === key ? 'rgba(201,168,76,0.1)' : 'none',
            color: active === key ? GOLD : MUTED,
            fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: active === key ? 600 : 400,
            cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            {label}
            {count > 0 && (
              <span style={{ background: active === key ? GOLD : BORDER, color: active === key ? '#000' : MUTED, borderRadius: 10, padding: '0 6px', fontSize: 10, fontWeight: 700 }}>{count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export function OrdersEmptyState({ navigate }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '60px 32px', gap: 16 }}>
      <div style={{ width: 80, height: 80, borderRadius: 20, background: CARD, border: `1px solid ${BORDER}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke={BORDER} strokeWidth="1.5" strokeLinecap="round">
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2"/>
        </svg>
      </div>
      <div style={{ textAlign: 'center' }}>
        <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: TEXT, margin: '0 0 6px' }}>Sem pedidos ainda</p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: MUTED, margin: 0, lineHeight: 1.6 }}>Quando fizeres a tua primeira compra aparecerá aqui</p>
      </div>
      <button onClick={() => navigate?.('/home')} style={{ padding: '13px 28px', borderRadius: 14, border: 'none', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, cursor: 'pointer', marginTop: 8 }}>
        Começar a comprar
      </button>
    </div>
  )
}
