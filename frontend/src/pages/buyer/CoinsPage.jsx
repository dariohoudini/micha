import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * CoinsPage — /coins
 *
 * AliExpress Complete 2025 CH 5 — Coins hub.
 *
 * Sections implemented:
 *   §5.2  Daily check-in calendar with streak day → coin reward
 *   §5.3  Today's coin-earning task list with progress + caps
 *   §5.7  Coin balance display (drives PDP & checkout discounts)
 *
 * Skipped (out of scope for a single-turn build):
 *   §5.4–§5.6  Lucky Forest / Coins Park / MergeBoss mini-games.
 *              The doc says these are dedicated 2D game canvases
 *              built on top of the coin-tasks API. Stubs are listed
 *              in the task list (they award coins via the same
 *              /tasks/complete endpoint) but their gameplay UI is
 *              left for follow-up.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const TASK_LABELS = {
  browse_3m:     { l: 'Navegar 3 minutos', icon: '👀' },
  add_wishlist:  { l: 'Adicionar à lista de desejos', icon: '❤️' },
  share_product: { l: 'Partilhar um produto', icon: '↗️' },
  follow_store:  { l: 'Seguir uma loja', icon: '⭐' },
  lucky_forest:  { l: 'Lucky Forest — regar árvore', icon: '🌳' },
  coins_park:    { l: 'Coins Park — girar', icon: '🎰' },
  merge_boss:    { l: 'MergeBoss — subir nível', icon: '🧩' },
}

export default function CoinsPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState(null)
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)

  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }

  const load = () => Promise.allSettled([
    client.get('/api/v1/loyalty/coins/check-in/'),
    client.get('/api/v1/loyalty/coins/tasks/'),
  ]).then(([s, t]) => {
    if (s.status === 'fulfilled') setStatus(s.value.data)
    if (t.status === 'fulfilled') setTasks(t.value.data?.tasks || [])
  })

  useEffect(() => {
    track('coins.open', {})
    load().finally(() => setLoading(false))
  }, [])

  const checkIn = async () => {
    setBusy(true)
    try {
      const res = await client.post('/api/v1/loyalty/coins/check-in/')
      track('coins.checked_in', { coins: res.data.coins_awarded, streak: res.data.streak_day })
      show(`+${res.data.coins_awarded} moedas! Streak ${res.data.streak_day} dias 🔥`)
      await load()
    } catch (e) {
      show(e.response?.data?.detail || 'Erro.', 'error')
    } finally { setBusy(false) }
  }

  const doTask = async (task) => {
    setBusy(true)
    try {
      const res = await client.post('/api/v1/loyalty/coins/tasks/complete/', { task })
      track('coins.task_completed', { task, coins: res.data.coins_awarded })
      show(`+${res.data.coins_awarded} moedas!`)
      await load()
    } catch (e) {
      show(e.response?.data?.detail || 'Limite diário atingido.', 'error')
    } finally { setBusy(false) }
  }

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>🪙 Moedas</h1>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 100px' }}>
        {loading || !status ? (
          <div style={{ height: 200, background: '#141414', borderRadius: 16, animation: 'pulse 1.4s ease-in-out infinite' }}>
            <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.45}}`}</style>
          </div>
        ) : (
          <>
            {/* Balance hero */}
            <div style={{ background: 'linear-gradient(135deg, rgba(201,168,76,0.22), rgba(201,168,76,0.05))', border: '1px solid rgba(201,168,76,0.35)', borderRadius: 18, padding: 22, textAlign: 'center', marginBottom: 16 }}>
              <p style={{ ...S, fontSize: 11, color: '#BFBFBF', textTransform: 'uppercase', letterSpacing: '0.08em' }}>O seu saldo</p>
              <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 44, fontWeight: 700, color: '#C9A84C', marginTop: 4 }}>
                🪙 {status.balance}
              </p>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 14 }}>1 moeda ≈ 1 Kz no checkout</p>
              <button onClick={() => navigate('/coins/games')}
                style={{ padding: '10px 20px', borderRadius: 12, border: '1px solid rgba(201,168,76,0.5)', background: 'rgba(0,0,0,0.25)', ...S, fontSize: 12, fontWeight: 700, color: '#C9A84C', cursor: 'pointer' }}>
                🎮 Abrir Jogos
              </button>
            </div>

            {/* Check-in calendar */}
            <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 16, padding: 16, marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <p style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFF' }}>Check-in diário</p>
                  <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>
                    Streak: <span style={{ color: '#C9A84C', fontWeight: 700 }}>{status.streak_day} dia(s) 🔥</span>
                  </p>
                </div>
                <button onClick={checkIn} disabled={busy || status.already_checked_in}
                  style={{ padding: '10px 18px', borderRadius: 10, border: 'none', background: status.already_checked_in ? '#2A2A2A' : '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: status.already_checked_in ? '#555' : '#0A0A0A', cursor: status.already_checked_in ? 'not-allowed' : 'pointer' }}>
                  {status.already_checked_in ? `✓ Hoje (+${status.today_coins})` : `Check-in +${status.next_reward}`}
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
                {(status.last_7 || []).map((d, i) => (
                  <div key={i} style={{ textAlign: 'center', padding: '8px 0', borderRadius: 8, background: d.checked ? 'rgba(201,168,76,0.18)' : '#0F0F0F', border: d.checked ? '1px solid rgba(201,168,76,0.35)' : '1px solid #1A1A1A' }}>
                    <div style={{ ...S, fontSize: 16 }}>{d.checked ? '🪙' : '○'}</div>
                    <p style={{ ...S, fontSize: 9, color: '#9A9A9A', marginTop: 2 }}>{new Date(d.date).getDate()}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Tasks */}
            <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Ganhe mais moedas hoje</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {tasks.map(t => {
                const cfg = TASK_LABELS[t.task] || { l: t.task, icon: '🎁' }
                const done = t.remaining === 0
                return (
                  <button key={t.task} onClick={() => doTask(t.task)} disabled={busy || done}
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, cursor: done ? 'not-allowed' : 'pointer', textAlign: 'left', opacity: done ? 0.55 : 1 }}>
                    <div style={{ fontSize: 24 }}>{cfg.icon}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ ...S, fontSize: 13, color: '#FFF', fontWeight: 500 }}>{cfg.l}</p>
                      <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>
                        {t.done_today}/{t.daily_cap} hoje · +{t.coins_per} 🪙 cada
                      </p>
                    </div>
                    <span style={{ ...S, fontSize: 12, fontWeight: 700, color: done ? '#10b981' : '#C9A84C' }}>
                      {done ? '✓' : `+${t.coins_per}`}
                    </span>
                  </button>
                )
              })}
            </div>
          </>
        )}
      </div>
    </BuyerLayout>
  )
}
