import { useRef } from 'react'
import { CATEGORIES } from './mockData'

export default function CategoryPills({ selected, onSelect }) {
  const ref = useRef(null)

  return (
    <div
      ref={ref}
      style={{
        display: 'flex',
        gap: 8,
        overflowX: 'auto',
        padding: '0 16px',
        scrollbarWidth: 'none',
        WebkitOverflowScrolling: 'touch',
      }}
    >
      <style>{`.cat-scroll::-webkit-scrollbar { display: none; }`}</style>
      {CATEGORIES.map(cat => {
        const active = selected === cat.id
        return (
          <button
            key={cat.id}
            onClick={() => onSelect(cat.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 16px',
              borderRadius: 50,
              border: `1.5px solid ${active ? '#C9A84C' : '#2A2A2A'}`,
              background: active ? '#C9A84C' : '#141414',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
              transition: 'all 0.2s ease',
            }}
          >
            <span style={{ fontSize: 13 }}>{cat.icon}</span>
            <span style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 13, fontWeight: active ? 600 : 400,
              color: active ? '#0A0A0A' : '#9A9A9A',
            }}>
              {cat.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
