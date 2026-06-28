import { useNavigate } from 'react-router-dom'
import { track } from '@/lib/userTrack'

const BackIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M19 12H5M12 5l-7 7 7 7" />
  </svg>
)

// §1.2 — Back button behaviour. If the user landed via deep link
// and the history stack is empty, plain `navigate(-1)` would either
// no-op or pop them out of the app. AliExpress spec is: "if stack
// empty: navigate('HomeScreen')" — same fallback here.
const safeGoBack = (navigate) => {
  try { track('button.tap', { id: 'header_back' }) } catch {}
  if (typeof window !== 'undefined'
      && window.history
      && window.history.length > 1) {
    navigate(-1)
  } else {
    navigate('/home', { replace: true })
  }
}

export default function PageHeader({
  title,
  subtitle,
  onBack,
  backTo,
  right,
  badge,
  transparent = false,
}) {
  const navigate = useNavigate()
  const handleBack = onBack
    || (backTo ? () => navigate(backTo) : () => safeGoBack(navigate))
  const showBack = onBack !== null

  return (
    <header
      style={{
        paddingTop: 'var(--page-top)',
        paddingLeft: 16,
        paddingRight: 16,
        paddingBottom: 16,
        flexShrink: 0,
        background: transparent ? 'transparent' : '#0A0A0A',
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        minHeight: 36,
      }}>
        {/* Left: back + title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
          {showBack !== false && (
            <button
              onClick={handleBack}
              aria-label="Voltar"
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 4,
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              <BackIcon />
            </button>
          )}

          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h1 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 22,
                fontWeight: 700,
                color: '#FFFFFF',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}>
                {title}
              </h1>
              {badge}
            </div>
            {subtitle && (
              <p style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 12,
                color: '#9A9A9A',
                marginTop: 2,
              }}>
                {subtitle}
              </p>
            )}
          </div>
        </div>

        {/* Right actions */}
        {right && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {right}
          </div>
        )}
      </div>
    </header>
  )
}
