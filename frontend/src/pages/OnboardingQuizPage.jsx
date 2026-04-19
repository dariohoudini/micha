import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitOnboardingQuiz } from '@/api/ai'

const CATEGORIES = [
  { id: 'Moda', label: 'Moda', emoji: '👗' },
  { id: 'Tecnologia', label: 'Tecnologia', emoji: '📱' },
  { id: 'Beleza', label: 'Beleza', emoji: '💄' },
  { id: 'Casa & Jardim', label: 'Casa & Jardim', emoji: '🏠' },
  { id: 'Desporto', label: 'Desporto', emoji: '⚽' },
  { id: 'Alimentação', label: 'Alimentação', emoji: '🛒' },
  { id: 'Acessórios', label: 'Acessórios', emoji: '💍' },
  { id: 'Crianças', label: 'Crianças', emoji: '🧸' },
  { id: 'Calçado', label: 'Calçado', emoji: '👟' },
  { id: 'Electrónica', label: 'Electrónica', emoji: '💻' },
]

const BUDGET_OPTIONS = [
  { id: '0-5000', label: 'Até 5 000 Kz', min: 0, max: 5000 },
  { id: '5000-20000', label: '5 000 – 20 000 Kz', min: 5000, max: 20000 },
  { id: '20000-50000', label: '20 000 – 50 000 Kz', min: 20000, max: 50000 },
  { id: '50000+', label: 'Mais de 50 000 Kz', min: 50000, max: 999999 },
]

const SHOPPING_FOR_OPTIONS = [
  { id: 'self', label: 'Para mim próprio(a)', icon: '🧍' },
  { id: 'family', label: 'Para a família', icon: '👨‍👩‍👧' },
  { id: 'gifts', label: 'Para ofertas', icon: '🎁' },
  { id: 'business', label: 'Para o negócio', icon: '💼' },
]

const PROVINCES = [
  'Luanda', 'Benguela', 'Huambo', 'Huíla', 'Cabinda',
  'Uíge', 'Namibe', 'Malanje', 'Bié', 'Moxico',
  'Cunene', 'Cuando Cubango', 'Lunda Norte', 'Lunda Sul',
  'Kwanza Norte', 'Kwanza Sul', 'Bengo', 'Zaire',
]

const TOTAL_STEPS = 4

export default function OnboardingQuizPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [answers, setAnswers] = useState({
    categories: [],
    budget: null,
    shopping_for: null,
    province: 'Luanda',
  })

  const canContinue = () => {
    if (step === 1) return answers.categories.length >= 1
    if (step === 2) return !!answers.budget
    if (step === 3) return !!answers.shopping_for
    if (step === 4) return !!answers.province
    return false
  }

  const toggleCategory = (cat) => {
    setAnswers(prev => ({
      ...prev,
      categories: prev.categories.includes(cat)
        ? prev.categories.filter(c => c !== cat)
        : prev.categories.length >= 5
          ? prev.categories  // Max 5
          : [...prev.categories, cat],
    }))
  }

  const handleSubmit = async () => {
    setLoading(true)
    const budget = BUDGET_OPTIONS.find(b => b.id === answers.budget)
    try {
      await submitOnboardingQuiz({
        categories: answers.categories,
        budget_min: budget?.min || 0,
        budget_max: budget?.max || 999999,
        shopping_for: answers.shopping_for,
        province: answers.province,
        language: 'pt',
      })
      navigate('/home', { replace: true })
    } catch (err) {
      console.error('Quiz submission failed:', err)
      navigate('/home', { replace: true }) // Don't block user on error
    } finally {
      setLoading(false)
    }
  }

  const S = ({ children, color = '#C9A84C' }) => (
    <span style={{ color }}>{children}</span>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', padding: 'max(52px, env(safe-area-inset-top)) 0 0' }}>

      {/* Header */}
      <div style={{ padding: '0 20px 24px', flexShrink: 0 }}>
        {/* Progress bar */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
          {Array(TOTAL_STEPS).fill(0).map((_, i) => (
            <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i < step ? '#C9A84C' : '#1E1E1E', transition: 'background 0.3s' }} />
          ))}
        </div>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 8 }}>
          Passo {step} de {TOTAL_STEPS}
        </p>

        {step === 1 && <>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>
            O que gosta de <S>comprar?</S>
          </h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>
            Selecione até 5 categorias. Usaremos isto para personalizar o seu feed.
          </p>
        </>}
        {step === 2 && <>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>
            Qual é o seu <S>orçamento</S> habitual?
          </h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>
            Por compra. Ajuda-nos a mostrar produtos adequados ao seu bolso.
          </p>
        </>}
        {step === 3 && <>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>
            Para quem <S>compra?</S>
          </h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>
            Ajuda-nos a personalizar as sugestões.
          </p>
        </>}
        {step === 4 && <>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>
            Onde está <S>localizado?</S>
          </h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>
            Para mostrar vendedores próximos e calcular prazos de entrega.
          </p>
        </>}
      </div>

      {/* Content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 20px 20px' }}>

          {/* Step 1 — Categories */}
          {step === 1 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {CATEGORIES.map(cat => {
                const selected = answers.categories.includes(cat.id)
                return (
                  <button key={cat.id} onClick={() => toggleCategory(cat.id)}
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderRadius: 14, cursor: 'pointer', textAlign: 'left', border: `1.5px solid ${selected ? '#C9A84C' : '#1E1E1E'}`, background: selected ? 'rgba(201,168,76,0.1)' : '#141414', transition: 'all 0.2s' }}>
                    <span style={{ fontSize: 22 }}>{cat.emoji}</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: selected ? 600 : 400, color: selected ? '#C9A84C' : '#FFFFFF' }}>{cat.label}</span>
                    {selected && (
                      <div style={{ marginLeft: 'auto', width: 18, height: 18, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}

          {/* Step 2 — Budget */}
          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {BUDGET_OPTIONS.map(opt => {
                const selected = answers.budget === opt.id
                return (
                  <button key={opt.id} onClick={() => setAnswers(prev => ({ ...prev, budget: opt.id }))}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 20px', borderRadius: 14, cursor: 'pointer', border: `1.5px solid ${selected ? '#C9A84C' : '#1E1E1E'}`, background: selected ? 'rgba(201,168,76,0.1)' : '#141414', transition: 'all 0.2s' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: selected ? 600 : 400, color: selected ? '#C9A84C' : '#FFFFFF' }}>{opt.label}</span>
                    {selected && (
                      <div style={{ width: 22, height: 22, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}

          {/* Step 3 — Shopping for */}
          {step === 3 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {SHOPPING_FOR_OPTIONS.map(opt => {
                const selected = answers.shopping_for === opt.id
                return (
                  <button key={opt.id} onClick={() => setAnswers(prev => ({ ...prev, shopping_for: opt.id }))}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '20px 16px', borderRadius: 14, cursor: 'pointer', border: `1.5px solid ${selected ? '#C9A84C' : '#1E1E1E'}`, background: selected ? 'rgba(201,168,76,0.1)' : '#141414', transition: 'all 0.2s' }}>
                    <span style={{ fontSize: 28 }}>{opt.icon}</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: selected ? 600 : 400, color: selected ? '#C9A84C' : '#FFFFFF', textAlign: 'center' }}>{opt.label}</span>
                  </button>
                )
              })}
            </div>
          )}

          {/* Step 4 — Province */}
          {step === 4 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {PROVINCES.map(province => {
                const selected = answers.province === province
                return (
                  <button key={province} onClick={() => setAnswers(prev => ({ ...prev, province }))}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px', borderRadius: 12, cursor: 'pointer', border: `1.5px solid ${selected ? '#C9A84C' : '#1E1E1E'}`, background: selected ? 'rgba(201,168,76,0.1)' : '#141414', transition: 'all 0.2s' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: selected ? 600 : 400, color: selected ? '#C9A84C' : '#FFFFFF' }}>{province}</span>
                    {selected && (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Footer buttons */}
      <div style={{ padding: '16px 20px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0, display: 'flex', gap: 10 }}>
        {step > 1 && (
          <button onClick={() => setStep(s => s - 1)} className="btn-secondary" style={{ width: 'auto', padding: '1rem 20px' }}>
            Anterior
          </button>
        )}
        {step < TOTAL_STEPS ? (
          <button onClick={() => setStep(s => s + 1)} className="btn-primary" disabled={!canContinue()} style={{ flex: 1, opacity: canContinue() ? 1 : 0.4 }}>
            Continuar
          </button>
        ) : (
          <button onClick={handleSubmit} className="btn-primary" disabled={!canContinue() || loading} style={{ flex: 1, opacity: canContinue() && !loading ? 1 : 0.4 }}>
            {loading ? 'A personalizar...' : '🚀 Ver o meu feed personalizado'}
          </button>
        )}
      </div>
    </div>
  )
}
