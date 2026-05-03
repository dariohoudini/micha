export default function Spinner({ size = 24, color = '#C9A84C', strokeWidth = 2.5, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}
      role="status"
      aria-label="Carregando"
    >
      <circle cx="12" cy="12" r="10" stroke={color} strokeWidth={strokeWidth} strokeOpacity="0.15" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
    </svg>
  )
}

export function FullPageSpinner() {
  return (
    <div
      role="status"
      aria-label="Carregando"
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        background: '#0A0A0A',
      }}
    >
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
        <circle cx="12" cy="12" r="10" stroke="#C9A84C" strokeWidth="2" strokeOpacity="0.15" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>
        A carregar…
      </p>
    </div>
  )
}
