import { useState, useEffect, useRef } from 'react'
import { BANNERS } from './mockData'

export default function PromoBanner() {
  const [current, setCurrent] = useState(0)
  const timerRef = useRef(null)

  const startTimer = () => {
    timerRef.current = setInterval(() => {
      setCurrent(c => (c + 1) % BANNERS.length)
    }, 3500)
  }

  useEffect(() => {
    startTimer()
    return () => clearInterval(timerRef.current)
  }, [])

  const goTo = (i) => {
    clearInterval(timerRef.current)
    setCurrent(i)
    startTimer()
  }

  return (
    <div style={{ padding: '0 16px', marginBottom: 4 }}>
      <div style={{
        borderRadius: 20,
        overflow: 'hidden',
        height: 160,
        position: 'relative',
      }}>
        {BANNERS.map((banner, i) => (
          <div
            key={banner.id}
            style={{
              position: 'absolute', inset: 0,
              background: banner.bg,
              display: 'flex', flexDirection: 'column',
              justifyContent: 'center',
              padding: '24px 24px',
              opacity: i === current ? 1 : 0,
              transition: 'opacity 0.5s ease',
              pointerEvents: i === current ? 'auto' : 'none',
            }}
          >
            {/* Express icon */}
            <div style={{ marginBottom: 10 }}>
              <svg width="28" height="28" viewBox="0 0 24 24"
                fill={banner.textColor === '#0A0A0A' ? '#0A0A0A' : banner.textColor}
                opacity="0.4">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </div>

            <h2 style={{
              fontFamily: "'Playfair Display', serif",
              fontSize: 22, fontWeight: 700,
              color: banner.textColor,
              lineHeight: 1.2,
              whiteSpace: 'pre-line',
              marginBottom: 6,
            }}>
              {banner.title}
            </h2>
            <p style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 12, color: banner.textColor,
              opacity: 0.7,
            }}>
              {banner.subtitle}
            </p>

            {/* CTA */}
            <div style={{
              position: 'absolute', right: 20, bottom: 20,
              background: banner.textColor === '#0A0A0A' ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.1)',
              border: `1px solid ${banner.textColor === '#0A0A0A' ? 'rgba(0,0,0,0.2)' : 'rgba(255,255,255,0.2)'}`,
              borderRadius: 20,
              padding: '6px 14px',
            }}>
              <span style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 11, fontWeight: 600,
                color: banner.textColor,
              }}>
                Ver mais →
              </span>
            </div>
          </div>
        ))}

        {/* Dots */}
        <div style={{
          position: 'absolute', bottom: 12, left: 20,
          display: 'flex', gap: 5,
        }}>
          {BANNERS.map((_, i) => (
            <button
              key={i}
              onClick={() => goTo(i)}
              style={{
                width: i === current ? 18 : 5,
                height: 5, borderRadius: 3,
                background: i === current ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.35)',
                border: 'none', cursor: 'pointer', padding: 0,
                transition: 'all 0.3s ease',
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
