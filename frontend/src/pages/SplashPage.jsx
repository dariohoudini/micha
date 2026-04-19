import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SplashPage() {
  const navigate = useNavigate()
  const [phase, setPhase] = useState('enter') // enter → logo → exit

  useEffect(() => {
    const t1 = setTimeout(() => setPhase('logo'), 300)
    const t2 = setTimeout(() => setPhase('exit'), 2200)
    const t3 = setTimeout(() => navigate('/language'), 2700)
    return () => [t1, t2, t3].forEach(clearTimeout)
  }, [navigate])

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: '#0A0A0A',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {/* Kente/Capulana geometric background */}
      <svg
        style={{
          position: 'absolute', inset: 0, width: '100%', height: '100%',
          opacity: phase === 'logo' ? 0.07 : 0,
          transition: 'opacity 1s ease',
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id="kente" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
            <rect width="40" height="40" fill="none" />
            <rect x="0" y="0" width="20" height="20" fill="#C9A84C" opacity="0.6" />
            <rect x="20" y="20" width="20" height="20" fill="#C9A84C" opacity="0.6" />
            <rect x="5" y="5" width="10" height="10" fill="#0A0A0A" />
            <rect x="25" y="25" width="10" height="10" fill="#0A0A0A" />
            <line x1="0" y1="20" x2="40" y2="20" stroke="#C9A84C" strokeWidth="0.5" opacity="0.4" />
            <line x1="20" y1="0" x2="20" y2="40" stroke="#C9A84C" strokeWidth="0.5" opacity="0.4" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#kente)" />
      </svg>

      {/* Radial glow behind logo */}
      <div style={{
        position: 'absolute',
        width: 280, height: 280,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(201,168,76,0.15) 0%, transparent 70%)',
        opacity: phase === 'logo' ? 1 : 0,
        transition: 'opacity 0.8s ease',
      }} />

      {/* Logo group */}
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
        opacity: phase === 'logo' ? 1 : 0,
        transform: phase === 'logo' ? 'translateY(0) scale(1)' : 'translateY(16px) scale(0.95)',
        transition: 'opacity 0.6s ease, transform 0.6s ease',
      }}>
        {/* Gold shopping bag icon */}
        <svg width="72" height="72" viewBox="0 0 72 72" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="12" y="24" width="48" height="38" rx="6" fill="#C9A84C" />
          <path d="M24 24V20C24 13.373 29.373 8 36 8C42.627 8 48 13.373 48 20V24" stroke="#C9A84C" strokeWidth="3.5" strokeLinecap="round" fill="none" />
          <rect x="12" y="24" width="48" height="10" rx="0" fill="#A67C35" opacity="0.4" />
          {/* M mark */}
          <path d="M26 50V38L32 46L36 40L40 46L46 38V50" stroke="#0A0A0A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          {/* Speed lines */}
          <line x1="50" y1="42" x2="58" y2="42" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
          <line x1="52" y1="46" x2="58" y2="46" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
          <line x1="54" y1="38" x2="58" y2="38" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
        </svg>

        {/* Wordmark */}
        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 38,
            fontWeight: 700,
            color: '#C9A84C',
            letterSpacing: '-0.5px',
            lineHeight: 1,
          }}>
            MICHA
          </div>
          <div style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 11,
            fontWeight: 500,
            color: '#E2C47A',
            letterSpacing: '0.35em',
            textTransform: 'uppercase',
            marginTop: 4,
          }}>
            Express
          </div>
        </div>
      </div>

      {/* Bottom tagline */}
      <div style={{
        position: 'absolute', bottom: 52,
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 12,
        color: '#9A9A9A',
        letterSpacing: '0.1em',
        opacity: phase === 'logo' ? 1 : 0,
        transition: 'opacity 0.6s ease 0.4s',
      }}>
        Angola · Entrega Rápida
      </div>
    </div>
  )
}
