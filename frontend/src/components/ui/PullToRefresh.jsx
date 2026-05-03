import { useRef, useState, useCallback } from 'react'
import Spinner from './Spinner'

const THRESHOLD = 72

export default function PullToRefresh({ onRefresh, children, disabled = false }) {
  const [pullY, setPullY] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const startY = useRef(0)
  const containerRef = useRef(null)
  const pulling = pullY > THRESHOLD * 0.4

  const handleTouchStart = useCallback((e) => {
    if (disabled || refreshing) return
    const el = containerRef.current
    if (!el || el.scrollTop > 0) return
    startY.current = e.touches[0].clientY
  }, [disabled, refreshing])

  const handleTouchMove = useCallback((e) => {
    if (!startY.current || refreshing) return
    const delta = e.touches[0].clientY - startY.current
    if (delta > 0 && containerRef.current?.scrollTop <= 0) {
      const clamped = Math.min(delta * 0.5, THRESHOLD * 1.2)
      setPullY(clamped)
    }
  }, [refreshing])

  const handleTouchEnd = useCallback(async () => {
    if (pullY >= THRESHOLD) {
      setRefreshing(true)
      setPullY(0)
      try {
        await onRefresh?.()
      } finally {
        setRefreshing(false)
      }
    } else {
      setPullY(0)
    }
    startY.current = 0
  }, [pullY, onRefresh])

  const progress = Math.min(pullY / THRESHOLD, 1)
  const rotation = progress * 360

  return (
    <div style={{ position: 'relative', height: '100%', overflow: 'hidden' }}>
      {/* Pull indicator */}
      {(pulling || refreshing) && (
        <div
          aria-live="polite"
          aria-label={refreshing ? 'A actualizar' : 'Solte para actualizar'}
          style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            height: refreshing ? 56 : pullY,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            zIndex: 10,
            transition: refreshing ? 'height 0.2s ease' : undefined,
          }}
        >
          {refreshing ? (
            <Spinner size={20} />
          ) : (
            <div style={{
              transform: `rotate(${rotation}deg)`,
              transition: 'transform 0.1s ease',
              opacity: progress,
              color: '#C9A84C',
            }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
            </div>
          )}
        </div>
      )}

      {/* Scrollable content */}
      <div
        ref={containerRef}
        className="screen"
        style={{
          height: '100%',
          transform: refreshing ? 'translateY(56px)' : pullY > 0 ? `translateY(${pullY}px)` : undefined,
          transition: pullY === 0 ? 'transform 0.3s ease' : undefined,
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {children}
      </div>
    </div>
  )
}
