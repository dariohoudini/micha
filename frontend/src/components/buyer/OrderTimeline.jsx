const STEPS = [
  { key: 'pending',   label: 'Pedido recebido',   icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2' },
  { key: 'confirmed', label: 'Pedido confirmado',  icon: 'M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4 12 14.01l-3-3' },
  { key: 'shipped',   label: 'Em trânsito',        icon: 'M5 17H3a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2H5zM14 3v5h5M17 21v-8H7v8M7 3v5' },
  { key: 'delivered', label: 'Entregue',           icon: 'M20 12V22H4V12M22 7H2v5h20V7zM12 22V7M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z' },
]

const STATUS_INDEX = { pending: 0, confirmed: 1, shipped: 2, delivered: 3 }

export default function OrderTimeline({ status = 'pending', timestamps = {} }) {
  const currentIndex = STATUS_INDEX[status] ?? 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {STEPS.map((step, i) => {
        const done = i <= currentIndex
        const active = i === currentIndex
        return (
          <div key={step.key} style={{ display: 'flex', gap: 14, position: 'relative' }}>
            {/* Line */}
            {i < STEPS.length - 1 && (
              <div style={{
                position: 'absolute', left: 15, top: 32, bottom: 0, width: 2,
                background: i < currentIndex ? '#C9A84C' : '#2A2A2A',
                transition: 'background 0.3s',
              }} />
            )}

            {/* Icon circle */}
            <div style={{
              width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
              background: done ? '#C9A84C' : '#1E1E1E',
              border: `2px solid ${done ? '#C9A84C' : '#2A2A2A'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.3s',
              zIndex: 1,
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke={done ? '#0A0A0A' : '#555'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d={step.icon} />
              </svg>
            </div>

            {/* Content */}
            <div style={{ paddingBottom: i < STEPS.length - 1 ? 24 : 0, paddingTop: 4 }}>
              <p style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 14, fontWeight: active ? 600 : 400,
                color: done ? '#FFFFFF' : '#555',
              }}>
                {step.label}
              </p>
              {timestamps[step.key] && (
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>
                  {timestamps[step.key]}
                </p>
              )}
              {active && !timestamps[step.key] && (
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', marginTop: 2 }}>
                  Em progresso...
                </p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
