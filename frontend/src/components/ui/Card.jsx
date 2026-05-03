export default function Card({
  children,
  padding = 16,
  elevated = false,
  pressable = false,
  onClick,
  style = {},
  className = '',
}) {
  return (
    <div
      role={pressable || onClick ? 'button' : undefined}
      tabIndex={pressable || onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick(e) : undefined}
      className={className}
      style={{
        background: elevated ? '#262626' : '#1E1E1E',
        border: '1px solid #2A2A2A',
        borderRadius: 16,
        padding,
        boxShadow: elevated ? '0 4px 12px rgba(0,0,0,0.5)' : undefined,
        cursor: pressable || onClick ? 'pointer' : undefined,
        transition: pressable || onClick ? 'opacity 0.15s ease, transform 0.12s ease' : undefined,
        WebkitTapHighlightColor: 'transparent',
        ...style,
      }}
      onMouseDown={onClick ? e => { e.currentTarget.style.transform = 'scale(0.985)'; e.currentTarget.style.opacity = '0.9' } : undefined}
      onMouseUp={onClick ? e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.opacity = '1' } : undefined}
      onTouchStart={onClick ? e => { e.currentTarget.style.transform = 'scale(0.985)'; e.currentTarget.style.opacity = '0.9' } : undefined}
      onTouchEnd={onClick ? e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.opacity = '1' } : undefined}
    >
      {children}
    </div>
  )
}
