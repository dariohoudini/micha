import { useState, useRef, useEffect } from 'react'

export default function LazyImage({
  src,
  alt = '',
  width,
  height,
  style = {},
  placeholderColor = '#1E1E1E',
  className = '',
  objectFit = 'cover',
}) {
  const [status, setStatus] = useState('idle') // idle | loading | loaded | error
  const [visible, setVisible] = useState(false)
  const imgRef = useRef(null)

  // Intersection Observer for lazy loading
  useEffect(() => {
    if (!src) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          setStatus('loading')
          observer.disconnect()
        }
      },
      { rootMargin: '200px' } // Start loading 200px before visible
    )
    if (imgRef.current) observer.observe(imgRef.current)
    return () => observer.disconnect()
  }, [src])

  return (
    <div
      ref={imgRef}
      className={className}
      style={{
        position: 'relative',
        overflow: 'hidden',
        background: placeholderColor,
        width, height,
        ...style,
      }}
    >
      {/* Shimmer placeholder while loading */}
      {status !== 'loaded' && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'linear-gradient(90deg, #1E1E1E 25%, #2A2A2A 50%, #1E1E1E 75%)',
          backgroundSize: '800px 100%',
          animation: 'shimmer 1.4s ease-in-out infinite',
        }}>
          <style>{`@keyframes shimmer { 0% { background-position: -400px 0; } 100% { background-position: 400px 0; } }`}</style>
        </div>
      )}

      {/* Error fallback */}
      {status === 'error' && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#1E1E1E',
        }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
            stroke="rgba(255,255,255,0.15)" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </div>
      )}

      {/* Actual image */}
      {visible && src && (
        <img
          src={src}
          alt={alt}
          onLoad={() => setStatus('loaded')}
          onError={() => setStatus('error')}
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            objectFit,
            opacity: status === 'loaded' ? 1 : 0,
            transition: 'opacity 0.3s ease',
          }}
          loading="lazy"
          decoding="async"
        />
      )}
    </div>
  )
}
