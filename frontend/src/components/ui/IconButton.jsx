import { forwardRef } from 'react'

const SIZES = {
  sm: { box: 32, radius: 8,  padding: 6 },
  md: { box: 40, radius: 10, padding: 8 },
  lg: { box: 48, radius: 12, padding: 10 },
}

const IconButton = forwardRef(({
  icon,
  'aria-label': ariaLabel,
  size = 'md',
  variant = 'ghost',
  badge,
  disabled = false,
  onClick,
  style = {},
  ...props
}, ref) => {
  const s = SIZES[size] || SIZES.md

  const bgMap = {
    ghost:   'transparent',
    surface: '#1E1E1E',
    gold:    'rgba(201,168,76,0.12)',
  }

  return (
    <button
      ref={ref}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      style={{
        position: 'relative',
        width: s.box,
        height: s.box,
        borderRadius: s.radius,
        padding: s.padding,
        background: bgMap[variant] || 'transparent',
        border: variant === 'surface' ? '1px solid #2A2A2A' : 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#FFFFFF',
        flexShrink: 0,
        transition: 'opacity 0.15s ease, transform 0.1s ease',
        WebkitTapHighlightColor: 'transparent',
        ...style,
      }}
      onMouseDown={e => { if (!disabled) e.currentTarget.style.transform = 'scale(0.9)' }}
      onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)' }}
      onTouchStart={e => { if (!disabled) e.currentTarget.style.transform = 'scale(0.9)' }}
      onTouchEnd={e => { e.currentTarget.style.transform = 'scale(1)' }}
      {...props}
    >
      {icon}
      {badge !== undefined && badge > 0 && (
        <span
          aria-label={`${badge} notificações`}
          style={{
            position: 'absolute',
            top: -3, right: -3,
            minWidth: 16, height: 16,
            borderRadius: 8,
            background: '#C9A84C',
            color: '#0A0A0A',
            fontSize: 9,
            fontWeight: 800,
            fontFamily: "'DM Sans', sans-serif",
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1.5px solid #0A0A0A',
            padding: '0 3px',
          }}
        >
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  )
})

IconButton.displayName = 'IconButton'
export default IconButton
