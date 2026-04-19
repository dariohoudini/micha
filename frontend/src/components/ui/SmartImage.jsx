import { useState, useRef } from 'react'
import { useInView } from 'react-intersection-observer'

/**
 * SmartImage — Production-grade image component
 * - Lazy loads when entering viewport
 * - Shows blur placeholder while loading
 * - Falls back gracefully on error
 * - Supports color placeholders for products
 */
export default function SmartImage({
  src,
  alt,
  width,
  height,
  placeholderColor = '#1E1E1E',
  className = '',
  style = {},
  objectFit = 'cover',
  priority = false,
  onLoad,
  onError,
}) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const { ref, inView } = useInView({
    triggerOnce: true,
    rootMargin: '200px', // Start loading 200px before visible
    skip: priority,      // Priority images load immediately
  })

  const shouldLoad = priority || inView

  const handleLoad = () => {
    setLoaded(true)
    onLoad?.()
  }

  const handleError = () => {
    setError(true)
    onError?.()
  }

  return (
    <div
      ref={ref}
      style={{
        position: 'relative',
        width: width || '100%',
        height: height || '100%',
        background: placeholderColor,
        overflow: 'hidden',
        ...style,
      }}
      className={className}
    >
      {/* Loading shimmer */}
      {!loaded && !error && (
        <div style={{
          position: 'absolute', inset: 0,
          background: `linear-gradient(90deg, ${placeholderColor} 25%, rgba(255,255,255,0.05) 50%, ${placeholderColor} 75%)`,
          backgroundSize: '200% 100%',
          animation: 'shimmer 1.5s infinite',
        }} />
      )}

      {/* Error fallback */}
      {error && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: placeholderColor,
        }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
            stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </div>
      )}

      {/* Actual image */}
      {shouldLoad && !error && (
        <img
          src={src}
          alt={alt}
          onLoad={handleLoad}
          onError={handleError}
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            objectFit,
            opacity: loaded ? 1 : 0,
            transition: 'opacity 0.3s ease',
          }}
        />
      )}

      <style>{`
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
      `}</style>
    </div>
  )
}
