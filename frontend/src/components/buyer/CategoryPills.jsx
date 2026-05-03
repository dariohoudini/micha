import { useRef } from 'react'
import { useCategories } from '@/hooks/useQueries'

const FALLBACK = [
  { id: 'all',     name: 'Tudo',        icon: '◈' },
  { id: 'fashion', name: 'Moda',        icon: '👗' },
  { id: 'tech',    name: 'Tecnologia',  icon: '📱' },
  { id: 'home',    name: 'Casa',        icon: '🏠' },
  { id: 'beauty',  name: 'Beleza',      icon: '✨' },
  { id: 'food',    name: 'Alimentação', icon: '🛒' },
  { id: 'sport',   name: 'Desporto',    icon: '⚽' },
  { id: 'kids',    name: 'Crianças',    icon: '🧸' },
]

export default function CategoryPills({ selected, onSelect }) {
  const ref = useRef(null)
  const { data: apiCats, isLoading } = useCategories()

  const cats = apiCats?.length
    ? [{ id: 'all', name: 'Tudo', icon: '◈' }, ...apiCats]
    : FALLBACK

  return (
    <div
      ref={ref}
      role="tablist"
      aria-label="Categorias"
      style={{
        display: 'flex',
        gap: 8,
        overflowX: 'auto',
        padding: '0 16px',
        scrollbarWidth: 'none',
        WebkitOverflowScrolling: 'touch',
      }}
    >
      {isLoading
        ? Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ width: 80, height: 36, borderRadius: 50, flexShrink: 0 }} />
          ))
        : cats.map(cat => {
            const active = selected === cat.id
            return (
              <button
                key={cat.id}
                role="tab"
                aria-selected={active}
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
                  {cat.name || cat.label}
                </span>
              </button>
            )
          })
      }
    </div>
  )
}
