import { useState, useRef } from 'react'
import { haptic } from '@/hooks/useUX'

export default function SwipeToDelete({ children, onDelete, deleteLabel = 'Eliminar' }) {
  const [swipeX, setSwipeX] = useState(0)
  const [deleting, setDeleting] = useState(false)
  const startX = useRef(0)
  const THRESHOLD = 80

  const onTouchStart = (e) => { startX.current = e.touches[0].clientX }
  const onTouchMove = (e) => {
    const dx = e.touches[0].clientX - startX.current
    if (dx < 0) setSwipeX(Math.max(dx, -110))
  }
  const onTouchEnd = async () => {
    if (swipeX < -THRESHOLD) {
      haptic.error()
      setDeleting(true)
      await onDelete?.()
    } else {
      setSwipeX(0)
    }
  }

  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 14 }}>
      {/* Delete background */}
      <div style={{
        position: 'absolute', right: 0, top: 0, bottom: 0,
        width: 110, background: '#EF4444',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        borderRadius: '0 14px 14px 0',
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
        </svg>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#fff' }}>{deleteLabel}</span>
      </div>
      {/* Content */}
      <div
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        style={{
          transform: `translateX(${swipeX}px)`,
          transition: swipeX === 0 ? 'transform 0.3s ease' : 'none',
          opacity: deleting ? 0 : 1,
          transition: deleting ? 'opacity 0.2s' : swipeX === 0 ? 'transform 0.3s ease' : 'none',
        }}
      >
        {children}
      </div>
    </div>
  )
}
