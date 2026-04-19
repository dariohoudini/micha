/**
 * FormField — Accessible form field wrapper
 * Wraps React Hook Form with proper aria attributes and error display
 */
export function FormField({ label, error, required, hint, children, htmlFor }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {label && (
        <label
          htmlFor={htmlFor}
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 12, fontWeight: 500,
            color: error ? '#F87171' : '#9A9A9A',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
          }}
        >
          {label}
          {required && <span style={{ color: '#dc2626', marginLeft: 3 }} aria-hidden="true">*</span>}
        </label>
      )}

      {children}

      {hint && !error && (
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>
          {hint}
        </p>
      )}

      {error && (
        <p
          role="alert"
          aria-live="polite"
          style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#F87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </p>
      )}
    </div>
  )
}

/**
 * Input — accessible input with ref forwarding for React Hook Form
 */
import { forwardRef } from 'react'

export const Input = forwardRef(function Input(
  { error, type = 'text', id, ...props },
  ref
) {
  return (
    <input
      ref={ref}
      id={id}
      type={type}
      aria-invalid={error ? 'true' : 'false'}
      aria-describedby={error ? `${id}-error` : undefined}
      className="input-base"
      style={{ borderColor: error ? 'rgba(220,38,38,0.5)' : undefined }}
      {...props}
    />
  )
})

/**
 * PhoneInput — +244 prefix + accessible input
 */
export const PhoneInput = forwardRef(function PhoneInput({ error, id, ...props }, ref) {
  return (
    <div style={{ display: 'flex' }} role="group" aria-label="Número de telefone">
      <div
        aria-hidden="true"
        style={{
          display: 'flex', alignItems: 'center', padding: '0 14px',
          background: '#1E1E1E', border: '1px solid #2A2A2A',
          borderRight: 'none', borderRadius: '12px 0 0 12px',
          fontFamily: "'DM Sans', sans-serif", fontSize: 14,
          color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap',
          userSelect: 'none',
        }}
      >
        🇦🇴 +244
      </div>
      <input
        ref={ref}
        id={id}
        type="tel"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={9}
        aria-label="Número de telefone (sem prefixo)"
        aria-invalid={error ? 'true' : 'false'}
        className="input-base"
        style={{
          borderRadius: '0 12px 12px 0', flex: 1,
          borderColor: error ? 'rgba(220,38,38,0.5)' : undefined,
        }}
        {...props}
      />
    </div>
  )
})

/**
 * ErrorBanner — form-level error display
 */
export function ErrorBanner({ message }) {
  if (!message) return null
  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        padding: '12px 16px', borderRadius: 12,
        background: 'rgba(220,38,38,0.1)',
        border: '1px solid rgba(220,38,38,0.3)',
        fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#F87171',
        display: 'flex', alignItems: 'flex-start', gap: 8,
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#F87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }}>
        <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      {message}
    </div>
  )
}
