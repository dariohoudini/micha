import { useState, useEffect } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const GREEN = '#059669'

const DEFAULT_CHALLENGES = [
  { id: 'first_purchase', icon: '🛍️', title: 'Primeira compra', desc: 'Faz a tua primeira compra na MICHA', points: 100, progress: 0, total: 1 },
  { id: 'first_review', icon: '⭐', title: 'Primeira avaliação', desc: 'Avalia um produto que compraste', points: 50, progress: 0, total: 1 },
  { id: 'refer_friend', icon: '👥', title: 'Convida um amigo', desc: 'O teu amigo regista-se com o teu código', points: 200, progress: 0, total: 1 },
  { id: 'daily_login', icon: '📅', title: 'Visita diária', desc: 'Entra na MICHA 7 dias seguidos', points: 75, progress: 3, total: 7 },
  { id: 'wishlist_5', icon: '❤️', title: 'Lista de desejos', desc: 'Adiciona 5 produtos à wishlist', points: 30, progress: 2, total: 5 },
]

export default function MichaChallenges() {
  const [challenges, setChallenges] = useState(DEFAULT_CHALLENGES)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    client.get('/api/v1/auth/loyalty/')
      .then(r => {
        if (r.data.challenges) setChallenges(r.data.challenges)
      })
      .catch(() => {})
  }, [])

  const visible = expanded ? challenges : challenges.slice(0, 3)

  return (
    <div style={{ padding: '0 16px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
          Desafios MICHA
        </h3>
        <button onClick={() => setExpanded(!expanded)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: GOLD, fontFamily: "'DM Sans', sans-serif", fontSize: 12 }}>
          {expanded ? 'Ver menos' : 'Ver todos'}
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {visible.map(ch => {
          const pct = Math.min((ch.progress / ch.total) * 100, 100)
          const done = pct >= 100
          return (
            <div key={ch.id} style={{ background: CARD, borderRadius: 12, border: `1px solid ${done ? 'rgba(5,150,105,0.3)' : BORDER}`, padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: done ? 'rgba(5,150,105,0.15)' : 'rgba(201,168,76,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>
                {ch.icon}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: done ? GREEN : TEXT, margin: 0 }}>{ch.title}</p>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: GOLD }}>+{ch.points} ⭐</span>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 6px' }}>{ch.desc}</p>
                <div style={{ height: 4, background: BORDER, borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: done ? GREEN : GOLD, borderRadius: 2, transition: 'width 0.5s ease' }} />
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '4px 0 0' }}>
                  {done ? '✓ Concluído' : `${ch.progress}/${ch.total}`}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
