import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import client from '@/api/client'
import { patchGuestProfile, completeOnboarding } from '@/lib/guestProfile'

const STEPS = [
  { id: 'categories', question: 'O que mais gosta de comprar?', options: ['Moda','Electrónica','Casa','Beleza','Desporto','Alimentação'] },
  { id: 'budget', question: 'Qual o seu orçamento habitual?', options: ['Menos de 5.000 Kz','5.000–20.000 Kz','20.000–50.000 Kz','Mais de 50.000 Kz'] },
  { id: 'shopping_for', question: 'Para quem costuma comprar?', options: ['Para mim','Para a família','Para oferecer','Para o negócio'] },
  { id: 'province', question: 'Em que província está?', options: ['Luanda','Benguela','Huambo','Huíla','Cabinda','Outra'] },
]

export default function OnboardingQuizPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({})
  const [loading, setLoading] = useState(false)

  const current = STEPS[step]

  const select = async (option) => {
    const newAnswers = { ...answers, [current.id]: option }
    setAnswers(newAnswers)

    if (step < STEPS.length - 1) {
      setStep(s => s + 1)
    } else {
      setLoading(true)
      // First-Run doc CH5/CH11 — write the setup answers to the PII-free
      // GUEST profile (no account needed) so they seed the feed now and
      // carry onto the account at signup. Interests are the cold-start
      // signal; province refines the locale.
      patchGuestProfile({
        interests: newAnswers.categories ? [newAnswers.categories] : [],
        locale: newAnswers.province ? { province: newAnswers.province } : undefined,
      })
      completeOnboarding(false)
      // Keep the authed taste-profile seed too, for a logged-in user
      // running the quiz (harmless 401 for a guest).
      try {
        await client.post('/api/v1/ai/onboarding-quiz/', newAnswers)
      } catch {}
      navigate('/home')
    }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', padding: '60px 24px 40px' }}>
      {/* Progress */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 40 }}>
        {STEPS.map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= step ? '#C9A84C' : '#1E1E1E', transition: 'background 0.3s' }} />
        ))}
      </div>

      <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
        {step + 1} de {STEPS.length}
      </p>
      <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 32, lineHeight: 1.3 }}>
        {current.question}
      </h1>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {current.options.map(option => (
          <button key={option} onClick={() => select(option)} disabled={loading}
            style={{ padding: '16px 20px', borderRadius: 14, border: '1.5px solid #2A2A2A', background: '#141414', ...S, fontSize: 15, color: '#FFFFFF', cursor: 'pointer', textAlign: 'left', transition: 'border-color 0.2s' }}>
            {option}
          </button>
        ))}
      </div>

      <button onClick={() => navigate('/home')} style={{ marginTop: 'auto', background: 'none', border: 'none', ...S, fontSize: 13, color: '#9A9A9A', cursor: 'pointer', paddingTop: 20 }}>
        Saltar
      </button>
    </div>
  )
}
