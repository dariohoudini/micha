import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const languages = [
  {
    code: 'pt',
    label: 'Português',
    sublabel: 'Angola',
    flag: (
      <svg width="36" height="36" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
        <clipPath id="circle"><circle cx="18" cy="18" r="18" /></clipPath>
        <g clipPath="url(#circle)">
          <rect width="36" height="18" fill="#CC0000" />
          <rect y="18" width="36" height="18" fill="#000000" />
          {/* Machete and gear (simplified Angola emblem) */}
          <circle cx="18" cy="18" r="6" fill="none" stroke="#FFCC00" strokeWidth="1.5" />
          <line x1="18" y1="10" x2="18" y2="26" stroke="#FFCC00" strokeWidth="1.2" />
          <line x1="10" y1="18" x2="26" y2="18" stroke="#FFCC00" strokeWidth="1.2" />
        </g>
      </svg>
    ),
  },
  {
    code: 'en',
    label: 'English',
    sublabel: 'International',
    flag: (
      <svg width="36" height="36" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
        <clipPath id="circle2"><circle cx="18" cy="18" r="18" /></clipPath>
        <g clipPath="url(#circle2)">
          <rect width="36" height="36" fill="#012169" />
          <line x1="0" y1="0" x2="36" y2="36" stroke="white" strokeWidth="5" />
          <line x1="36" y1="0" x2="0" y2="36" stroke="white" strokeWidth="5" />
          <line x1="0" y1="0" x2="36" y2="36" stroke="#C8102E" strokeWidth="3" />
          <line x1="36" y1="0" x2="0" y2="36" stroke="#C8102E" strokeWidth="3" />
          <rect x="14" y="0" width="8" height="36" fill="white" />
          <rect x="0" y="14" width="36" height="8" fill="white" />
          <rect x="15.5" y="0" width="5" height="36" fill="#C8102E" />
          <rect x="0" y="15.5" width="36" height="5" fill="#C8102E" />
        </g>
      </svg>
    ),
  },
]

export default function LanguagePage() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState('pt')

  const handleContinue = () => {
    localStorage.setItem('lang', selected)
    navigate('/welcome')
  }

  return (
    <div className="screen" style={{
      minHeight: '100%',
      background: '#0A0A0A',
      display: 'flex',
      flexDirection: 'column',
      padding: '0 24px',
    }}>
      {/* Top decoration */}
      <div style={{
        height: 4,
        background: 'linear-gradient(90deg, #C9A84C, #E2C47A, #C9A84C)',
        marginBottom: 0,
      }} />

      {/* Header */}
      <div style={{ paddingTop: 56, paddingBottom: 40 }}>
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 12,
          color: '#C9A84C',
          letterSpacing: '0.2em',
          textTransform: 'uppercase',
          marginBottom: 12,
        }}>
          Bem-vindo · Welcome
        </p>
        <h1 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 32,
          fontWeight: 700,
          color: '#FFFFFF',
          lineHeight: 1.2,
        }}>
          Escolha o seu idioma
        </h1>
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 14,
          color: '#9A9A9A',
          marginTop: 8,
        }}>
          Choose your language
        </p>
      </div>

      {/* Language options */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
        {languages.map((lang) => {
          const active = selected === lang.code
          return (
            <button
              key={lang.code}
              onClick={() => setSelected(lang.code)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                padding: '18px 20px',
                borderRadius: 16,
                background: active ? 'rgba(201,168,76,0.1)' : '#141414',
                border: `1.5px solid ${active ? '#C9A84C' : '#2A2A2A'}`,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                textAlign: 'left',
              }}
            >
              {lang.flag}
              <div style={{ flex: 1 }}>
                <div style={{
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: 16,
                  fontWeight: 600,
                  color: active ? '#C9A84C' : '#FFFFFF',
                }}>
                  {lang.label}
                </div>
                <div style={{
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: 12,
                  color: '#9A9A9A',
                  marginTop: 2,
                }}>
                  {lang.sublabel}
                </div>
              </div>
              {/* Radio indicator */}
              <div style={{
                width: 22, height: 22,
                borderRadius: '50%',
                border: `2px solid ${active ? '#C9A84C' : '#2A2A2A'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.2s ease',
              }}>
                {active && (
                  <div style={{
                    width: 10, height: 10,
                    borderRadius: '50%',
                    background: '#C9A84C',
                  }} />
                )}
              </div>
            </button>
          )
        })}
      </div>

      {/* CTA */}
      <div style={{ padding: '32px 0 48px' }}>
        <button className="btn-primary" onClick={handleContinue}>
          Continuar
        </button>
      </div>
    </div>
  )
}
