import { useState, useRef } from 'react'

/**
 * SafeImage — AliExpress Complete 2025 CH 26.4.
 *
 * Drop-in replacement for <img> that handles CDN failures by
 * showing a "tap to retry" placeholder. After a single hard fail
 * we keep the original `src` mounted but invisible, so a click
 * triggers an explicit cache-busted retry. Three retries max.
 */

export default function SafeImage({ src, alt = '', style = {}, fallback = null, ...rest }) {
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const ref = useRef()
  const cacheBuster = attempt > 0 ? (src.includes('?') ? '&' : '?') + `_r=${attempt}` : ''

  const retry = (e) => {
    e?.stopPropagation?.()
    if (attempt >= 3) return
    setAttempt(a => a + 1)
    setFailed(false)
  }

  if (failed) {
    return (
      <button onClick={retry} aria-label="Repetir imagem"
        style={{
          ...style,
          background: '#1E1E1E', border: 'none', cursor: attempt < 3 ? 'pointer' : 'default',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: 4,
        }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
        {attempt < 3 && <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>Tocar para repetir</span>}
      </button>
    )
  }

  if (!src) return fallback || <div style={{ ...style, background: '#1E1E1E' }} />

  return (
    <img ref={ref} src={src + cacheBuster} alt={alt} style={style}
      loading="lazy" decoding="async"
      onError={() => setFailed(true)}
      {...rest} />
  )
}
