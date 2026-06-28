import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { track } from '@/lib/userTrack'

/**
 * OnboardingCarouselPage — User Process Flow Chapter 2.
 *
 * Shown on the very first launch (when AsyncStorage / localStorage
 * key ``micha_onboarded`` is missing). 4 slides:
 *   1) Welcome
 *   2) Fast Delivery
 *   3) Sell Too (cross-sell seller flow)
 *   4) Get Started — CTAs to Register or Log In
 *
 * Behaviours from the doc:
 *   • Dot indicators at the bottom (tap to jump).
 *   • Swipe gesture (horizontal drag → next/prev).
 *   • [SKIP] from slides 1-3 sets ``micha_onboarded=true`` and
 *     jumps to Login.
 *   • [NEXT] / [GET STARTED] advances.
 *   • On Slide 4: [CREATE ACCOUNT] (orange) and [LOG IN] (outline).
 *   • Every action POSTs to UserEvent via track() so the funnel
 *     into registration is measurable.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }
const STORAGE_KEY = 'micha_onboarded'

const SLIDES = [
  {
    emoji: '🛍️',
    headline: '10.000+ produtos entregues à sua porta',
    sub: 'O marketplace que mais cresce em Angola.',
    bg: 'linear-gradient(135deg, #1a1208 0%, #0A0A0A 100%)',
  },
  {
    emoji: '🛵',
    headline: 'Entrega expressa em Luanda — no mesmo dia',
    sub: 'Acompanhe o seu pedido em tempo real do vendedor até si.',
    bg: 'linear-gradient(135deg, #0c1818 0%, #0A0A0A 100%)',
  },
  {
    emoji: '🏪',
    headline: 'Abra a sua loja gratuitamente',
    sub: 'Alcance compradores em todo o país. Sem taxas de listagem.',
    bg: 'linear-gradient(135deg, #181208 0%, #0A0A0A 100%)',
  },
  {
    emoji: '🎉',
    headline: 'Pronto para começar?',
    sub: '',
    bg: 'linear-gradient(135deg, #1a0c14 0%, #0A0A0A 100%)',
    isFinal: true,
  },
]

export default function OnboardingCarouselPage() {
  const navigate = useNavigate()
  const [idx, setIdx] = useState(0)
  const startX = useRef(null)
  const total = SLIDES.length

  // Log carousel entry.
  useEffect(() => { track('onboarding.open', {}) }, [])
  useEffect(() => { track('onboarding.slide_view', { slide: idx + 1 }) }, [idx])

  const finish = (action) => {
    try { localStorage.setItem(STORAGE_KEY, 'true') } catch {}
    track('onboarding.finish', { action, last_slide: idx + 1 })
    if (action === 'register') navigate('/register')
    else navigate('/login')
  }
  const next = () => {
    if (idx + 1 < total) {
      track('onboarding.next', { from: idx + 1, to: idx + 2 })
      setIdx(i => i + 1)
    }
  }
  const skip = () => {
    track('onboarding.skip', { from: idx + 1 })
    finish('skip')
  }

  const onTouchStart = (e) => { startX.current = e.touches?.[0]?.clientX ?? null }
  const onTouchEnd = (e) => {
    if (startX.current === null) return
    const dx = (e.changedTouches?.[0]?.clientX ?? startX.current) - startX.current
    if (Math.abs(dx) > 50) {
      if (dx < 0 && idx + 1 < total) setIdx(i => i + 1)
      if (dx > 0 && idx > 0) setIdx(i => i - 1)
    }
    startX.current = null
  }

  const s = SLIDES[idx]
  return (
    <div className="screen"
      onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}
      style={{ minHeight: '100%', background: s.bg, display: 'flex', flexDirection: 'column', color: '#FFFFFF', transition: 'background 0.4s' }}>
      <div style={{ padding: 'max(56px, env(safe-area-inset-top)) 24px 0', display: 'flex', justifyContent: 'flex-end' }}>
        {!s.isFinal && (
          <button onClick={skip} style={{ background: 'transparent', border: 'none', cursor: 'pointer', ...S, fontSize: 13, color: '#9A9A9A' }}>
            Saltar
          </button>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px 32px', textAlign: 'center' }}>
        <div style={{ fontSize: 100, marginBottom: 24, lineHeight: 1 }}>{s.emoji}</div>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 12, lineHeight: 1.25 }}>
          {s.headline}
        </h1>
        {s.sub && <p style={{ ...S, fontSize: 14, color: '#BFBFBF', lineHeight: 1.55, maxWidth: 340 }}>{s.sub}</p>}
      </div>

      {/* Dots */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: '12px 0' }}>
        {SLIDES.map((_, i) => (
          <button key={i} onClick={() => setIdx(i)}
            aria-label={`Slide ${i + 1}`}
            style={{ width: i === idx ? 22 : 7, height: 7, borderRadius: 4, border: 'none', background: i === idx ? '#C9A84C' : 'rgba(255,255,255,0.25)', cursor: 'pointer', transition: 'all 0.2s' }} />
        ))}
      </div>

      <div style={{ padding: '20px 24px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {s.isFinal ? (
          <>
            <button onClick={() => finish('register')}
              style={{ padding: '15px 0', borderRadius: 14, border: 'none', background: '#C9A84C', ...S, fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
              Criar conta
            </button>
            <button onClick={() => finish('login')}
              style={{ padding: '14px 0', borderRadius: 14, border: '1.5px solid #C9A84C', background: 'transparent', ...S, fontSize: 14, fontWeight: 600, color: '#C9A84C', cursor: 'pointer' }}>
              Já tenho conta
            </button>
          </>
        ) : (
          <button onClick={next}
            style={{ padding: '15px 0', borderRadius: 14, border: 'none', background: '#C9A84C', ...S, fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            {idx === total - 2 ? 'Começar →' : 'Próximo →'}
          </button>
        )}
      </div>
    </div>
  )
}
