export default function Button({ children, variant = 'primary', onClick, disabled, className = '' }) {
  const base = variant === 'primary' ? 'btn-primary' : 'btn-secondary'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${disabled ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}
    >
      {children}
    </button>
  )
}
