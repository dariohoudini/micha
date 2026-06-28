import { useEffect, useRef, useState } from 'react'

/**
 * AutoPlayVideo — AliExpress Complete 2025 CH 4.5.
 *
 * Renders a `<video>` that:
 *   • Loads only when scrolled into viewport (IntersectionObserver).
 *   • Auto-plays muted + loops while visible (browser autoplay
 *     policies allow muted video).
 *   • Pauses when scrolled out of view (saves battery + bandwidth).
 *   • Tapping the video unmutes it.
 *   • A subtle "🔊" overlay when muted; "🔇" when unmuted.
 *
 * If `src` is missing, falls back to rendering `poster` as a still
 * image so product cards don't break.
 */

export default function AutoPlayVideo({ src, poster, style = {}, threshold = 0.6, onPlay }) {
  const ref = useRef()
  const [visible, setVisible] = useState(false)
  const [muted, setMuted] = useState(true)

  useEffect(() => {
    if (!ref.current) return
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) {
        setVisible(e.isIntersecting && e.intersectionRatio >= threshold)
      }
    }, { threshold: [0, threshold, 1] })
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [threshold])

  useEffect(() => {
    const v = ref.current
    if (!v) return
    if (visible) {
      v.play().then(() => onPlay?.()).catch(() => {})
    } else {
      v.pause()
    }
  }, [visible, onPlay])

  if (!src) {
    return poster ? <img src={poster} alt="" style={style} loading="lazy" /> : <div style={style} />
  }

  return (
    <div style={{ position: 'relative', ...style }} onClick={(e) => { e.stopPropagation(); setMuted(m => !m) }}>
      <video
        ref={ref}
        src={src}
        poster={poster}
        muted={muted}
        loop
        playsInline
        preload="metadata"
        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
      />
      <span style={{ position: 'absolute', bottom: 6, right: 6, padding: '2px 8px', borderRadius: 12, background: 'rgba(0,0,0,0.6)', color: '#FFFFFF', fontFamily: "'DM Sans', sans-serif", fontSize: 11, pointerEvents: 'none' }}>
        {muted ? '🔇' : '🔊'}
      </span>
    </div>
  )
}
