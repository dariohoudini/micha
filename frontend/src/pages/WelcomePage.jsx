import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const slides = [
  {
    icon: (
      <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="40" cy="40" r="40" fill="rgba(201,168,76,0.1)" />
        <rect x="20" y="28" width="40" height="32" rx="5" fill="#C9A84C" opacity="0.9" />
        <rect x="20" y="28" width="40" height="10" rx="0" fill="#A67C35" opacity="0.5" />
        <path d="M30 28V24C30 19.582 34.477 16 40 16C45.523 16 50 19.582 50 24V28" stroke="#C9A84C" strokeWidth="3" strokeLinecap="round" fill="none" />
        <path d="M32 48V40L37 46L40 42L43 46L48 40V48" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    ),
    title: 'Angola na palma\nda sua mão',
    subtitle: 'Milhares de produtos locais e internacionais, entregues onde você estiver.',
  },
  {
    icon: (
      <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="40" cy="40" r="40" fill="rgba(201,168,76,0.1)" />
        {/* Lightning bolt - express delivery */}
        <path d="M46 18L28 44H40L34 62L54 36H42L46 18Z" fill="#C9A84C" stroke="#A67C35" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    ),
    title: 'Entrega\nExpress',
    subtitle: 'Receba as suas encomendas rapidamente. Velocidade que você nunca viu em Angola.',
  },
  {
    icon: (
      <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="40" cy="40" r="40" fill="rgba(201,168,76,0.1)" />
        {/* Store/seller icon */}
        <rect x="18" y="36" width="44" height="26" rx="4" fill="#C9A84C" opacity="0.9" />
        <path d="M18 36L22 20H58L62 36" stroke="#C9A84C" strokeWidth="2.5" fill="none" strokeLinejoin="round" />
        <rect x="32" y="46" width="16" height="16" rx="3" fill="#0A0A0A" />
        <rect x="22" y="44" width="8" height="8" rx="2" fill="#0A0A0A" opacity="0.7" />
        <rect x="50" y="44" width="8" height="8" rx="2" fill="#0A0A0A" opacity="0.7" />
      </svg>
    ),
    title: 'Venda para\ntodo Angola',
    subtitle: 'Crie a sua loja em minutos. Gerencie produtos, pedidos e pagamentos num só lugar.',
  },
]

export default function WelcomePage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [animating, setAnimating] = useState(false)

  const goNext = () => {
    if (animating) return
    if (current < slides.length - 1) {
      setAnimating(true)
      setTimeout(() => {
        setCurrent((c) => c + 1)
        setAnimating(false)
      }, 200)
    } else {
      navigate('/login')
    }
  }

  const slide = slides[current]

  return (
    <div style={{
      minHeight: '100%',
      background: '#0A0A0A',
      display: 'flex',
      flexDirection: 'column',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Gold top bar */}
      <div style={{
        height: 3,
        background: 'linear-gradient(90deg, #C9A84C, #E2C47A, #C9A84C)',
      }} />

      {/* Skip */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end',
        padding: '20px 24px 0',
      }}>
        <button
          onClick={() => navigate('/login')}
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 13,
            color: '#9A9A9A',
            background: 'none', border: 'none', cursor: 'pointer',
          }}
        >
          Saltar
        </button>
      </div>

      {/* Slide content */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 32px',
        opacity: animating ? 0 : 1,
        transform: animating ? 'translateY(12px)' : 'translateY(0)',
        transition: 'opacity 0.2s ease, transform 0.2s ease',
      }}>
        {/* Icon */}
        <div style={{ marginBottom: 40 }}>
          {slide.icon}
        </div>

        {/* Title */}
        <h1 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 34,
          fontWeight: 700,
          color: '#FFFFFF',
          textAlign: 'center',
          lineHeight: 1.2,
          whiteSpace: 'pre-line',
          marginBottom: 16,
        }}>
          {slide.title}
        </h1>

        {/* Subtitle */}
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 15,
          color: '#9A9A9A',
          textAlign: 'center',
          lineHeight: 1.6,
          maxWidth: 280,
        }}>
          {slide.subtitle}
        </p>
      </div>

      {/* Bottom controls */}
      <div style={{ padding: '0 24px 48px' }}>
        {/* Dots */}
        <div style={{
          display: 'flex', justifyContent: 'center', gap: 8,
          marginBottom: 28,
        }}>
          {slides.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrent(i)}
              style={{
                width: i === current ? 24 : 8,
                height: 8,
                borderRadius: 4,
                background: i === current ? '#C9A84C' : '#2A2A2A',
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.3s ease',
                padding: 0,
              }}
            />
          ))}
        </div>

        {/* Next / Get Started button */}
        <button className="btn-primary" onClick={goNext}>
          {current < slides.length - 1 ? 'Próximo' : 'Começar'}
        </button>
      </div>
    </div>
  )
}
