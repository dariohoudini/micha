import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * CoinGamesPage — /coins/games
 *
 * AliExpress Complete 2025 CH 5.4–5.6 — three in-app coin-earning
 * mini-games consolidated under one screen with tabs:
 *
 *   🌳 Lucky Forest   §5.4  — water/grow/harvest a virtual tree
 *   🎰 Coins Park     §5.5  — slot spin with 3 daily free spins
 *   🧩 MergeBoss      §5.6  — drag-merge identical tiles
 *
 * Each game posts to the same /loyalty/coins/tasks/complete/
 * endpoint with task=lucky_forest|coins_park|merge_boss respectively,
 * which (a) credits the user's coins, (b) writes a row to
 * CoinTaskCompletion, (c) emits a UserEvent for analytics. Daily
 * caps are server-enforced (10/15/5 wins per day per game).
 *
 * Game state is kept in sessionStorage so closing the screen
 * doesn't lose progress within a single session. Out-of-session
 * progress is intentionally NOT persisted: the doc says each play
 * day is independent.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }
const FOREST_KEY = 'micha-game-forest-v1'

// ── Game 1: Lucky Forest ────────────────────────────────────────
function LuckyForest({ onWin }) {
  const [state, setState] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(FOREST_KEY) || '{}') } catch { return {} }
  })
  const { water = 0, growth = 0 } = state
  const stages = ['Semente', 'Rebento', 'Pequena', 'Jovem', 'Madura', 'Frutos']
  const stageIdx = Math.min(5, Math.floor(growth / 20))
  const ready = stageIdx === 5
  const emoji = ['🌱', '🌿', '🌾', '🌳', '🌳', '🍎'][stageIdx]

  const persist = (s) => {
    setState(s)
    try { sessionStorage.setItem(FOREST_KEY, JSON.stringify(s)) } catch {}
  }
  const drawWater = () => {
    if (water >= 100) return
    persist({ water: Math.min(100, water + 5), growth })
    track('game.forest.water_drawn', { water: water + 5 })
  }
  const pour = () => {
    if (water < 10 || ready) return
    persist({ water: water - 10, growth: Math.min(100, growth + 10) })
    track('game.forest.poured', { growth: growth + 10 })
  }
  const harvest = async () => {
    if (!ready) return
    try {
      const res = await client.post('/api/v1/loyalty/coins/tasks/complete/', { task: 'lucky_forest' })
      onWin(res.data.coins_awarded)
      persist({ water: 0, growth: 0 })
      track('game.forest.harvested', { coins: res.data.coins_awarded })
    } catch (e) {
      track('game.forest.harvest_failed', { error: e.response?.data?.detail || 'unknown' })
      alert(e.response?.data?.detail || 'Sem colheitas hoje — volte amanhã.')
    }
  }
  return (
    <div style={{ padding: 20, textAlign: 'center' }}>
      <div style={{ fontSize: 100, lineHeight: 1, marginBottom: 8, transition: 'all 0.4s' }}>{emoji}</div>
      <p style={{ ...S, fontSize: 14, color: '#FFF', fontWeight: 600 }}>{stages[stageIdx]}</p>
      <div style={{ height: 6, background: '#1E1E1E', borderRadius: 3, marginTop: 12, overflow: 'hidden' }}>
        <div style={{ width: `${growth}%`, height: '100%', background: '#10b981', transition: 'width 0.3s' }} />
      </div>
      <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>Crescimento {growth}/100</p>
      <div style={{ marginTop: 16, padding: 12, background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12 }}>
        <p style={{ ...S, fontSize: 12, color: '#FFF' }}>💧 Água: {water}/100</p>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button onClick={drawWater} disabled={water >= 100}
            style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: 'none', background: water >= 100 ? '#2A2A2A' : '#3b82f6', ...S, fontSize: 12, fontWeight: 700, color: '#FFF', cursor: water >= 100 ? 'not-allowed' : 'pointer' }}>+5 água</button>
          <button onClick={pour} disabled={water < 10 || ready}
            style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: 'none', background: (water < 10 || ready) ? '#2A2A2A' : '#10b981', ...S, fontSize: 12, fontWeight: 700, color: '#FFF', cursor: (water < 10 || ready) ? 'not-allowed' : 'pointer' }}>Regar (-10)</button>
        </div>
      </div>
      {ready && (
        <button onClick={harvest}
          style={{ width: '100%', marginTop: 16, padding: '16px 0', borderRadius: 14, border: 'none', background: 'linear-gradient(135deg, #C9A84C, #E2C47A)', ...S, fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          🍎 Colher e ganhar moedas!
        </button>
      )}
    </div>
  )
}

// ── Game 2: Coins Park (slot spin) ──────────────────────────────
function CoinsPark({ onWin }) {
  const [spinning, setSpinning] = useState(false)
  const [reels, setReels] = useState(['🪙', '🎁', '⭐'])
  const [lastWin, setLastWin] = useState(null)
  const SYMBOLS = ['🪙', '🎁', '⭐', '💎', '7️⃣', '🍒']

  const spin = async () => {
    if (spinning) return
    setSpinning(true)
    setLastWin(null)
    track('game.park.spin_started', {})
    // Animate reels for 1.4s, settling one by one.
    const ticks = setInterval(() => {
      setReels([SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)],
                SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)],
                SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)]])
    }, 80)
    setTimeout(async () => {
      clearInterval(ticks)
      try {
        const res = await client.post('/api/v1/loyalty/coins/tasks/complete/', { task: 'coins_park' })
        // Show a "winning" combo when server credited.
        setReels(['🪙', '🪙', '🪙'])
        setLastWin(res.data.coins_awarded)
        onWin(res.data.coins_awarded)
        track('game.park.spin_won', { coins: res.data.coins_awarded })
      } catch (e) {
        // Daily cap or other failure — show a non-winning combo.
        setReels(['🎁', '⭐', '💎'])
        setLastWin(0)
        track('game.park.spin_no_win', { reason: e.response?.data?.detail || '' })
      } finally {
        setSpinning(false)
      }
    }, 1400)
  }
  return (
    <div style={{ padding: 20, textAlign: 'center' }}>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'center', padding: 24, background: 'linear-gradient(135deg, #1a0c1a, #0A0A0A)', border: '2px solid #C9A84C', borderRadius: 18 }}>
        {reels.map((s, i) => (
          <div key={i} style={{ width: 70, height: 80, background: '#0A0A0A', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, border: '1px solid #2A2A2A', transition: 'all 0.1s' }}>{s}</div>
        ))}
      </div>
      {lastWin !== null && (
        <p style={{ ...S, fontSize: 14, color: lastWin > 0 ? '#10b981' : '#9A9A9A', marginTop: 14, fontWeight: 700 }}>
          {lastWin > 0 ? `🎉 Ganhou ${lastWin} moedas!` : 'Limite diário atingido — volte amanhã.'}
        </p>
      )}
      <button onClick={spin} disabled={spinning}
        style={{ width: '100%', marginTop: 20, padding: '16px 0', borderRadius: 14, border: 'none', background: spinning ? '#2A2A2A' : '#C9A84C', ...S, fontSize: 15, fontWeight: 700, color: spinning ? '#555' : '#0A0A0A', cursor: spinning ? 'not-allowed' : 'pointer' }}>
        {spinning ? 'A girar…' : '🎰 GIRAR (grátis)'}
      </button>
      <p style={{ ...S, fontSize: 10, color: '#9A9A9A', marginTop: 10 }}>15 girações grátis por dia · 3 moedas por vitória</p>
    </div>
  )
}

// ── Game 3: MergeBoss (simplified) ──────────────────────────────
function MergeBoss({ onWin }) {
  const [grid, setGrid] = useState(() => Array(9).fill(0).map(() => Math.floor(Math.random() * 3) + 1))
  const [dragIdx, setDragIdx] = useState(null)
  const [score, setScore] = useState(0)
  const tryMerge = async (from, to) => {
    if (from === to) return
    if (grid[from] === 0) return
    if (grid[from] !== grid[to]) return
    const next = [...grid]
    next[to] = next[to] + 1
    next[from] = Math.floor(Math.random() * 3) + 1  // spawn new tile
    setGrid(next)
    const newScore = score + next[to]
    setScore(newScore)
    track('game.merge.merge', { level: next[to], score: newScore })
    // Reward milestone: every level-5 reached
    if (next[to] >= 5) {
      try {
        const res = await client.post('/api/v1/loyalty/coins/tasks/complete/', { task: 'merge_boss' })
        onWin(res.data.coins_awarded)
        track('game.merge.milestone', { level: next[to], coins: res.data.coins_awarded })
      } catch { /* daily cap */ }
    }
  }
  return (
    <div style={{ padding: 20 }}>
      <p style={{ ...S, fontSize: 12, color: '#9A9A9A', textAlign: 'center', marginBottom: 4 }}>Score: <strong style={{ color: '#C9A84C' }}>{score}</strong></p>
      <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textAlign: 'center', marginBottom: 16 }}>Arraste para fundir peças iguais</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, maxWidth: 300, margin: '0 auto' }}>
        {grid.map((n, i) => (
          <div key={i}
            draggable={n > 0}
            onDragStart={() => setDragIdx(i)}
            onDragOver={e => e.preventDefault()}
            onDrop={() => { tryMerge(dragIdx, i); setDragIdx(null) }}
            style={{ aspectRatio: '1', background: n === 0 ? '#1E1E1E' : `hsl(${30 + n * 25}, 65%, 45%)`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: n > 0 ? 'grab' : 'default', ...S, fontSize: 28, fontWeight: 700, color: '#FFF', userSelect: 'none' }}>
            {n > 0 ? n : ''}
          </div>
        ))}
      </div>
      <p style={{ ...S, fontSize: 10, color: '#9A9A9A', textAlign: 'center', marginTop: 14 }}>Atinja nível 5 para ganhar moedas (5x por dia)</p>
    </div>
  )
}

export default function CoinGamesPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('forest')
  const [balance, setBalance] = useState(0)
  const [toast, setToast] = useState(null)
  useEffect(() => {
    track('coins.games.open', {})
    client.get('/api/v1/loyalty/coins/check-in/').then(r => setBalance(r.data?.balance || 0)).catch(() => {})
  }, [])
  const onWin = (coins) => {
    setBalance(b => b + coins)
    setToast(`+${coins} 🪙`)
    setTimeout(() => setToast(null), 1800)
  }
  const tabs = [
    { v: 'forest', l: '🌳 Lucky Forest' },
    { v: 'park',   l: '🎰 Coins Park' },
    { v: 'merge',  l: '🧩 MergeBoss' },
  ]
  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: '#C9A84C', color: '#0A0A0A', padding: '8px 18px', borderRadius: 14, ...S, fontSize: 16, fontWeight: 700 }}>{toast}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', flex: 1 }}>Jogos</h1>
        <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>🪙 {balance}</span>
      </div>
      <div style={{ display: 'flex', borderBottom: '1px solid #1A1A1A', padding: '0 12px' }}>
        {tabs.map(t => (
          <button key={t.v} onClick={() => setTab(t.v)}
            style={{ flex: 1, padding: '12px 0', background: 'none', border: 'none', cursor: 'pointer', ...S, fontSize: 12, fontWeight: tab === t.v ? 700 : 400, color: tab === t.v ? '#C9A84C' : '#9A9A9A', borderBottom: `2px solid ${tab === t.v ? '#C9A84C' : 'transparent'}`, marginBottom: -1 }}>{t.l}</button>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {tab === 'forest' && <LuckyForest onWin={onWin} />}
        {tab === 'park' && <CoinsPark onWin={onWin} />}
        {tab === 'merge' && <MergeBoss onWin={onWin} />}
      </div>
    </BuyerLayout>
  )
}
