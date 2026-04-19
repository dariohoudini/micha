import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore as useAuth } from '@/stores/authStore'

export default function ReferralPage() {
  const navigate = useNavigate()
  const user = useAuth(s => s.user)
  const [copied, setCopied] = useState(false)

  const referralCode = user?.referral_code || 'MICHA-XXXX'
  const referralUrl = `https://micha.ao/join?ref=${referralCode}`

  const handleCopy = () => {
    navigator.clipboard.writeText(referralCode).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => navigate('/profile')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Referências & Amigos</h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Hero */}
          <div style={{ borderRadius: 20, padding: 24, background: 'linear-gradient(135deg, #C9A84C 0%, #A67C35 100%)', textAlign: 'center' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(0,0,0,0.4)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: 12 }}>
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" />
            </svg>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#0A0A0A', marginBottom: 6 }}>Convide amigos</h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(0,0,0,0.6)', lineHeight: 1.5 }}>
              Ganhe pontos de fidelidade por cada amigo que se registar com o seu código.
            </p>
          </div>

          {/* Referral code */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', letterSpacing: '0.1em', textTransform: 'uppercase' }}>O seu código</p>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: 1, padding: '14px 16px', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, display: 'flex', alignItems: 'center' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 18, fontWeight: 700, color: '#C9A84C', letterSpacing: '0.1em' }}>{referralCode}</span>
              </div>
              <button onClick={handleCopy} style={{
                padding: '0 20px', borderRadius: 12, cursor: 'pointer', flexShrink: 0,
                background: copied ? '#059669' : '#C9A84C', border: 'none',
                fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#0A0A0A',
                transition: 'background 0.2s',
              }}>
                {copied ? '✓ Copiado' : 'Copiar'}
              </button>
            </div>
          </div>

          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {[{ label: 'Referências', value: '0' }, { label: 'Pontos ganhos', value: '0' }].map(stat => (
              <div key={stat.label} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16, textAlign: 'center' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 24, fontWeight: 700, color: '#C9A84C' }}>{stat.value}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 4 }}>{stat.label}</p>
              </div>
            ))}
          </div>

          {/* How it works */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>Como funciona</p>
            {[
              { step: '1', text: 'Partilhe o seu código com amigos' },
              { step: '2', text: 'O amigo regista-se com o seu código' },
              { step: '3', text: 'Ambos ganham pontos de fidelidade' },
            ].map(item => (
              <div key={item.step} style={{ display: 'flex', gap: 14, alignItems: 'center', padding: '12px 0', borderBottom: item.step !== '3' ? '1px solid #141414' : 'none' }}>
                <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>{item.step}</span>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>{item.text}</p>
              </div>
            ))}
          </div>

          <button className="btn-primary">
            Partilhar código
          </button>
        </div>
      </div>
    </div>
  )
}
