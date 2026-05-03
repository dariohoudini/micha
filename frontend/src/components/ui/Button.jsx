import { forwardRef } from 'react'

const SIZE = {
  sm:  { padding: '8px 14px', fontSize: 13, borderRadius: 10, gap: 6 },
  md:  { padding: '12px 20px', fontSize: 15, borderRadius: 12, gap: 8 },
  lg:  { padding: '16px 24px', fontSize: 16, borderRadius: 16, gap: 8 },
  xl:  { padding: '18px 28px', fontSize: 17, borderRadius: 16, gap: 10 },
  full: { padding: '16px', fontSize: 16, borderRadius: 16, gap: 8, width: '100%' },
}

const VARIANT_STYLES = {
  primary: {
    background: '#C9A84C',
    color: '#0A0A0A',
    border: 'none',
  },
  secondary: {
    background: 'transparent',
    color: '#C9A84C',
    border: '1.5px solid #C9A84C',
  },
  ghost: {
    background: 'transparent',
    color: '#C8C8C8',
    border: 'none',
  },
  danger: {
    background: 'rgba(239,68,68,0.12)',
    color: '#ef4444',
    border: '1px solid rgba(239,68,68,0.3)',
  },
  surface: {
    background: '#1E1E1E',
    color: '#FFFFFF',
    border: '1px solid #2A2A2A',
  },
  gold_ghost: {
    background: 'rgba(201,168,76,0.08)',
    color: '#C9A84C',
    border: '1px solid rgba(201,168,76,0.2)',
  },
}

const Spinner = ({ size = 16, color = 'currentColor' }) => (
  <svg
    width={size} height={size}
    viewBox="0 0 24 24" fill="none"
    style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="10" stroke={color} strokeWidth="2.5" strokeOpacity="0.2" />
    <path d="M12 2a10 10 0 0 1 10 10" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
  </svg>
)

const Button = forwardRef(({
  children,
  variant = 'primary',
  size = 'full',
  loading = false,
  disabled = false,
  leftIcon,
  rightIcon,
  onClick,
  type = 'button',
  className = '',
  style = {},
  'aria-label': ariaLabel,
  ...props
}, ref) => {
  const s = SIZE[size] || SIZE.full
  const v = VARIANT_STYLES[variant] || VARIANT_STYLES.primary
  const isDisabled = disabled || loading

  return (
    <button
      ref={ref}
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      aria-label={ariaLabel}
      aria-busy={loading}
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: s.gap,
        padding: s.padding,
        borderRadius: s.borderRadius,
        fontSize: s.fontSize,
        width: s.width,
        fontFamily: "'DM Sans', sans-serif",
        fontWeight: 600,
        letterSpacing: '0.02em',
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.45 : 1,
        transition: 'opacity 0.2s ease, transform 0.12s ease, box-shadow 0.2s ease',
        WebkitTapHighlightColor: 'transparent',
        WebkitUserSelect: 'none',
        userSelect: 'none',
        outline: 'none',
        whiteSpace: 'nowrap',
        position: 'relative',
        overflow: 'hidden',
        flexShrink: 0,
        ...v,
        ...style,
      }}
      onMouseDown={e => { if (!isDisabled) e.currentTarget.style.transform = 'scale(0.97)' }}
      onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)' }}
      onTouchStart={e => { if (!isDisabled) e.currentTarget.style.transform = 'scale(0.97)' }}
      onTouchEnd={e => { e.currentTarget.style.transform = 'scale(1)' }}
      {...props}
    >
      {loading ? <Spinner size={size === 'sm' ? 14 : 18} /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  )
})

Button.displayName = 'Button'
export default Button
