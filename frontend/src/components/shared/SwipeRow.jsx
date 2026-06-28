import { useState, useRef } from 'react'

/**
 * SwipeRow — AliExpress Complete 2025 CH 10.2.
 *
 * Left-swipe-to-reveal pattern: wraps content; on touch-drag left
 * exposes one or two action buttons. Click outside to dismiss.
 *
 * Props:
 *   children       — main content
 *   actions        — [{ label, color, onClick }, ...]  shown right-to-left
 *   maxReveal      — px width to reveal (auto from action count)
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

export default function SwipeRow({ children, actions = [], maxReveal }) {
  const [dx, setDx] = useState(0)
  const startX = useRef(null)
  const startDx = useRef(0)
  const widthPerBtn = 84
  const max = maxReveal || actions.length * widthPerBtn

  const onTouchStart = (e) => {
    startX.current = e.touches?.[0]?.clientX ?? null
    startDx.current = dx
  }
  const onTouchMove = (e) => {
    if (startX.current === null) return
    const cur = e.touches?.[0]?.clientX ?? startX.current
    const delta = cur - startX.current
    const next = Math.max(-max, Math.min(0, startDx.current + delta))
    setDx(next)
  }
  const onTouchEnd = () => {
    // Snap open if dragged > 40% of max, else snap closed.
    setDx(prev => Math.abs(prev) > max * 0.4 ? -max : 0)
    startX.current = null
  }
  const close = () => setDx(0)

  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 12 }}>
      {/* action buttons sit behind the content */}
      <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, display: 'flex' }}>
        {actions.map((a, i) => (
          <button key={i} onClick={() => { close(); a.onClick?.() }}
            style={{ width: widthPerBtn, padding: 0, background: a.color || '#ef4444', border: 'none', ...S, fontSize: 12, fontWeight: 700, color: '#FFFFFF', cursor: 'pointer' }}>
            {a.label}
          </button>
        ))}
      </div>
      <div
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        style={{ transform: `translateX(${dx}px)`, transition: startX.current === null ? 'transform 0.18s ease-out' : 'none', willChange: 'transform' }}
      >
        {children}
      </div>
    </div>
  )
}
