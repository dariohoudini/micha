import { useState, useRef } from 'react'

export default function ProductImageGallery({ images = [], placeholderColor = '#1E1E1E' }) {
  const [current, setCurrent] = useState(0)
  const startX = useRef(null)

  const handleTouchStart = (e) => { startX.current = e.touches[0].clientX }
  const handleTouchEnd = (e) => {
    if (startX.current === null) return
    const diff = startX.current - e.changedTouches[0].clientX
    if (Math.abs(diff) > 40) {
      if (diff > 0) setCurrent(c => Math.min(c + 1, images.length - 1))
      else setCurrent(c => Math.max(c - 1, 0))
    }
    startX.current = null
  }

  const hasImages = images.length > 0

  return (
    <div style={{ position: 'relative', width: '100%', aspectRatio: '1', background: placeholderColor, overflow: 'hidden' }}>
      {/* Images */}
      <div
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        style={{ display: 'flex', width: `${Math.max(images.length, 1) * 100}%`, height: '100%', transform: `translateX(-${current * (100 / Math.max(images.length, 1))}%)`, transition: 'transform 0.3s ease' }}
      >
        {hasImages ? images.map((img, i) => (
          <div key={i} style={{ width: `${100 / images.length}%`, height: '100%', flexShrink: 0 }}>
            <img src={img} alt={`Produto ${i + 1}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading={i === 0 ? 'eager' : 'lazy'} />
          </div>
        )) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
            </svg>
          </div>
        )}
      </div>

      {/* Dots */}
      {images.length > 1 && (
        <div style={{ position: 'absolute', bottom: 12, left: 0, right: 0, display: 'flex', justifyContent: 'center', gap: 5 }}>
          {images.map((_, i) => (
            <button key={i} onClick={() => setCurrent(i)}
              style={{ width: i === current ? 18 : 6, height: 6, borderRadius: 3, background: i === current ? '#C9A84C' : 'rgba(255,255,255,0.4)', border: 'none', cursor: 'pointer', padding: 0, transition: 'all 0.2s' }} />
          ))}
        </div>
      )}

      {/* Counter */}
      {images.length > 1 && (
        <div style={{ position: 'absolute', top: 12, right: 12, background: 'rgba(0,0,0,0.5)', borderRadius: 20, padding: '3px 8px' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#FFFFFF' }}>{current + 1}/{images.length}</span>
        </div>
      )}
    </div>
  )
}
