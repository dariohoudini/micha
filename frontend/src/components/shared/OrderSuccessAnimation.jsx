import { useEffect, useState } from 'react'
import { haptic } from '@/hooks/useUX'

export default function OrderSuccessAnimation({ onDone }) {
  const [phase, setPhase] = useState(0)

  useEffect(() => {
    haptic.success()
    const t1 = setTimeout(() => { setPhase(1); haptic.success() }, 300)
    const t2 = setTimeout(() => setPhase(2), 800)
    const t3 = setTimeout(() => { setPhase(3); onDone?.() }, 2000)
    return () => [t1, t2, t3].forEach(clearTimeout)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '40px 0' }}>
      <div style={{ position: 'relative', width: 100, height: 100 }}>
        {/* Expanding ring */}
        <div style={{
          position: 'absolute', inset: 0, borderRadius: '50%',
          background: 'rgba(5,150,105,0.15)',
          transform: phase >= 1 ? 'scale(1)' : 'scale(0)',
          transition: 'transform 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        }} />
        {/* Circle */}
        <div style={{
          position: 'absolute', inset: 8, borderRadius: '50%',
          background: phase >= 1 ? '#059669' : 'transparent',
          border: '3px solid #059669',
          transform: phase >= 1 ? 'scale(1)' : 'scale(0)',
          transition: 'all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) 0.1s',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {/* Checkmark */}
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            style={{ opacity: phase >= 2 ? 1 : 0, transform: phase >= 2 ? 'scale(1)' : 'scale(0)', transition: 'all 0.3s ease 0.2s' }}>
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        {/* Confetti particles */}
        {phase >= 2 && ['#C9A84C','#059669','#3B82F6','#EF4444','#F59E0B'].map((color, i) => (
          <div key={i} style={{
            position: 'absolute', width: 6, height: 6, borderRadius: '50%',
            background: color, top: '50%', left: '50%',
            animation: `confetti_${i} 0.8s ease-out forwards`,
          }} />
        ))}
      </div>
      <style>{`
        ${['#C9A84C','#059669','#3B82F6','#EF4444','#F59E0B'].map((_, i) => `
          @keyframes confetti_${i} {
            0% { transform: translate(-50%,-50%) scale(1); opacity: 1; }
            100% { transform: translate(${(i-2)*40}px, ${-60-i*10}px) scale(0); opacity: 0; }
          }
        `).join('')}
      `}</style>
      <div style={{ textAlign: 'center', opacity: phase >= 2 ? 1 : 0, transform: phase >= 2 ? 'translateY(0)' : 'translateY(10px)', transition: 'all 0.4s ease' }}>
        <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', margin: '0 0 6px' }}>Pedido confirmado!</p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', margin: 0 }}>O teu pedido está a ser processado</p>
      </div>
    </div>
  )
}
