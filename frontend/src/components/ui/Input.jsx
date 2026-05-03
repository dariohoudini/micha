import { forwardRef, useState, useId } from 'react'

const Input = forwardRef(({
  label,
  error,
  hint,
  leftIcon,
  rightElement,
  type = 'text',
  placeholder,
  disabled = false,
  required = false,
  optional = false,
  className = '',
  style = {},
  ...props
}, ref) => {
  const [focused, setFocused] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const id = useId()
  const errorId = error ? `${id}-error` : undefined
  const hintId = hint ? `${id}-hint` : undefined
  const isPassword = type === 'password'
  const inputType = isPassword ? (showPassword ? 'text' : 'password') : type

  const borderColor = error ? '#ef4444'
    : focused ? '#C9A84C'
    : '#2A2A2A'

  const boxShadow = error && focused ? '0 0 0 3px rgba(239,68,68,0.12)'
    : focused ? '0 0 0 3px rgba(201,168,76,0.12)'
    : 'none'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, ...style }} className={className}>
      {label && (
        <label
          htmlFor={id}
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 12,
            fontWeight: 600,
            color: error ? '#ef4444' : '#9A9A9A',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          {label}
          {required && <span style={{ color: '#C9A84C' }}>*</span>}
          {optional && <span style={{ color: '#555', fontWeight: 400, textTransform: 'none', fontSize: 11 }}>(opcional)</span>}
        </label>
      )}

      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        {leftIcon && (
          <div style={{
            position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)',
            color: focused ? '#C9A84C' : '#555',
            pointerEvents: 'none',
            transition: 'color 0.2s ease',
            display: 'flex',
          }}>
            {leftIcon}
          </div>
        )}

        <input
          ref={ref}
          id={id}
          type={inputType}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          aria-invalid={!!error}
          aria-describedby={[errorId, hintId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            width: '100%',
            padding: leftIcon ? '12px 42px 12px 42px' : isPassword ? '12px 44px 12px 16px' : '12px 16px',
            borderRadius: 12,
            fontSize: 15,
            fontFamily: "'DM Sans', sans-serif",
            outline: 'none',
            background: '#1E1E1E',
            border: `1px solid ${borderColor}`,
            color: disabled ? '#555' : '#FFFFFF',
            transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
            WebkitAppearance: 'none',
            boxShadow,
            cursor: disabled ? 'not-allowed' : 'text',
          }}
          {...props}
        />

        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(v => !v)}
            aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
            style={{
              position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)',
              background: 'none', border: 'none', cursor: 'pointer', padding: 4,
              color: '#555', display: 'flex', alignItems: 'center',
            }}
          >
            {showPassword ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            )}
          </button>
        )}

        {rightElement && !isPassword && (
          <div style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)' }}>
            {rightElement}
          </div>
        )}
      </div>

      {error && (
        <p id={errorId} role="alert" style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 12,
          color: '#ef4444',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </p>
      )}

      {hint && !error && (
        <p id={hintId} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>
          {hint}
        </p>
      )}
    </div>
  )
})

Input.displayName = 'Input'
export default Input
