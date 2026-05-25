/**
 * ResponsiveImage — Tier 7 format-negotiating image with blur placeholder.
 *
 * Distinct from <LazyImage>: this component focuses on FORMAT
 * negotiation (AVIF / WebP / fallback) via a <picture> element and
 * a backend that supports a ``?fmt=`` query param. <LazyImage>
 * focuses on the IntersectionObserver gating.
 *
 * When backend doesn't support ?fmt, set negotiate={false} (default)
 * and the component becomes a plain lazy <img> with shimmer.
 *
 * Format support detection happens at the browser layer — <source>
 * with `type="image/avif"` is silently ignored by browsers that don't
 * support it. No JS detection needed.
 */
import { useEffect, useRef, useState } from 'react'


export default function ResponsiveImage({
  src,
  alt = '',
  aspectRatio,
  srcSet,
  eager = false,
  negotiate = false,
  className,
  style,
  onLoad,
  onError,
  ...rest
}) {
  const ref = useRef(null)
  const [visible, setVisible] = useState(eager)
  const [loaded, setLoaded] = useState(false)
  const [errored, setErrored] = useState(false)

  useEffect(() => {
    if (eager || visible) return
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setVisible(true)
            io.disconnect()
            break
          }
        }
      },
      { rootMargin: '200px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [eager, visible])

  const wrapperStyle = {
    position: 'relative',
    width: '100%',
    aspectRatio,
    background: '#1E1E1E',
    overflow: 'hidden',
    ...style,
  }

  const imgStyle = {
    width: '100%', height: '100%', objectFit: 'cover',
    display: 'block',
    opacity: loaded ? 1 : 0,
    transition: 'opacity 220ms ease',
  }

  const renderImg = () => (
    <img
      src={visible ? src : undefined}
      alt={alt}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      srcSet={visible ? srcSet : undefined}
      onLoad={(e) => { setLoaded(true); onLoad?.(e) }}
      onError={(e) => { setErrored(true); onError?.(e) }}
      style={imgStyle}
      {...rest}
    />
  )

  return (
    <div ref={ref} className={className} style={wrapperStyle}>
      {!loaded && !errored && (
        <div
          aria-hidden="true"
          style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(110deg, #1E1E1E 8%, #2A2A2A 18%, #1E1E1E 33%)',
            backgroundSize: '200% 100%',
            animation: 'rimg-shimmer 1.4s ease infinite',
          }}
        />
      )}

      {visible && negotiate ? (
        <picture>
          <source srcSet={appendFmt(src, 'avif')} type="image/avif" />
          <source srcSet={appendFmt(src, 'webp')} type="image/webp" />
          {renderImg()}
        </picture>
      ) : (
        renderImg()
      )}

      {errored && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'rgba(255,255,255,0.3)', fontSize: 11,
          fontFamily: "'DM Sans', sans-serif",
        }}>
          Imagem indisponível
        </div>
      )}

      <style>{`
        @keyframes rimg-shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
      `}</style>
    </div>
  )
}


export function appendFmt(url, fmt) {
  if (!url) return url
  try {
    const u = new URL(url, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
    u.searchParams.set('fmt', fmt)
    return u.toString()
  } catch {
    return url + (url.includes('?') ? '&' : '?') + 'fmt=' + fmt
  }
}
