import { useEffect, useState } from 'react'
import client from '@/api/client'
import { haptic } from '@/hooks/useUX'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const S = { fontFamily: "'DM Sans', sans-serif" }

export default function DailyCheckinCard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [claiming, setClaiming] = useState(false)
  const [flash, setFlash] = useState(null) // "+8 pontos!"

  useEffect(() => {
    client.get('/api/v1/auth/checkin/')
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  const claim = async () => {
    if (claiming || data?.claimed_today) return
    setClaiming(true)
    try {
      const res = await client.post('/api/v1/auth/checkin/')
      setData(prev => ({
        ...(prev || {}),
        claimed_today: true,
        streak_days: res.data.streak_days,
        next_reward_points: prev?.next_reward_points || 0,
        points_balance: res.data.points_balance,
      }))
      setFlash(`+${res.data.points_awarded} pontos!`)
      haptic.success?.()
      setTimeout(() => setFlash(null), 2400)
    } catch (err) {
      // 401 / network — silent fail (anonymous users hit guard upstream)
    } finally {
      setClaiming(false)
    }
  }

  if (loading || !data) return null

  const streak = data.streak_days || 0
  const next = data.next_reward_points || 0
  const balance = data.points_balance || 0
  const claimed = !!data.claimed_today

  return (
    <div style={{
      margin: '0 16px 16px',
      borderRadius: 16,
      background: 'linear-gradient(135deg, #1a1408 0%, #2a1f0e 100%)',
      border: '1px solid rgba(201,168,76,0.25)',
      padding: 14,
      position: 'relative', overflow: 'hidden',
    }}>
      {/* +N pontos flash */}
      {flash && (
        <div style={{
          position: 'absolute', top: 12, right: 14,
          ...S, fontSize: 13, fontWeight: 700, color: GOLD,
          animation: 'fadeUp 2.2s ease-out forwards',
        }}>
          {flash}
          <style>{`@keyframes fadeUp{0%{opacity:0;transform:translateY(8px)}20%,80%{opacity:1;transform:translateY(0)}100%{opacity:0;transform:translateY(-12px)}}`}</style>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontSize: 16 }}>🪙</span>
            <p style={{ ...S, fontSize: 14, fontWeight: 700, color: TEXT, margin: 0 }}>Check-in diário</p>
          </div>
          <p style={{ ...S, fontSize: 11, color: MUTED, margin: '3px 0 0' }}>
            {streak > 0 && (claimed
              ? <>Sequência: <span style={{ color: GOLD, fontWeight: 600 }}>{streak} {streak === 1 ? 'dia' : 'dias'} 🔥</span></>
              : <>Não percas a sequência de {streak} {streak === 1 ? 'dia' : 'dias'}</>
            )}
            {streak === 0 && 'Recebe pontos todos os dias'}
          </p>
          <p style={{ ...S, fontSize: 11, color: MUTED, margin: '2px 0 0' }}>
            Saldo: <span style={{ color: TEXT }}>{balance.toLocaleString()}</span> pontos
            <span style={{ color: '#555' }}> · 100 pts = 1 Kz</span>
          </p>
        </div>
        <button
          onClick={claim}
          disabled={claimed || claiming}
          style={{
            flexShrink: 0, padding: '10px 16px', borderRadius: 12, border: 'none',
            background: claimed ? 'rgba(255,255,255,0.06)' : GOLD,
            ...S, fontSize: 12, fontWeight: 700,
            color: claimed ? MUTED : '#0A0A0A',
            cursor: claimed ? 'default' : 'pointer',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1,
            minWidth: 78,
          }}>
          {claiming ? '...' : claimed ? (
            <>
              <span style={{ fontSize: 14 }}>✓</span>
              <span style={{ fontSize: 9, fontWeight: 500 }}>Hoje</span>
            </>
          ) : (
            <>
              <span style={{ fontSize: 13, fontWeight: 800 }}>+{next}</span>
              <span style={{ fontSize: 9, fontWeight: 500, color: 'rgba(0,0,0,0.7)' }}>RECLAMAR</span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
