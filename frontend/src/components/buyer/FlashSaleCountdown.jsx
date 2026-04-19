import { useState, useEffect } from 'react'

function pad(n) { return String(n).padStart(2, '0') }

export default function FlashSaleCountdown({ endsAt }) {
  const [timeLeft, setTimeLeft] = useState({ h: 0, m: 0, s: 0 })

  useEffect(() => {
    const calc = () => {
      const diff = Math.max(0, endsAt - Date.now())
      setTimeLeft({
        h: Math.floor(diff / 3600000),
        m: Math.floor((diff % 3600000) / 60000),
        s: Math.floor((diff % 60000) / 1000),
      })
    }
    calc()
    const t = setInterval(calc, 1000)
    return () => clearInterval(t)
  }, [endsAt])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="#dc2626">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#FFFFFF', fontWeight: 600 }}>Termina em</span>
      {[timeLeft.h, timeLeft.m, timeLeft.s].map((v, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <span style={{
            background: '#dc2626', color: '#FFFFFF',
            fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700,
            padding: '2px 5px', borderRadius: 4, minWidth: 24, textAlign: 'center',
          }}>{pad(v)}</span>
          {i < 2 && <span style={{ color: '#dc2626', fontWeight: 700, fontSize: 12 }}>:</span>}
        </span>
      ))}
    </div>
  )
}
