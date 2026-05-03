/**
 * MICHA Hyper-Personalization — Personalised Price Signal
 * Shows context-aware price signals based on user history
 * "Melhor preço que viste" / "Abaixo da média" / "Preço sobe frequentemente"
 */
import { useState, useEffect } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const GREEN = '#059669'
const RED = '#EF4444'
const BLUE = '#3B82F6'

export default function PersonalisedPriceBadge({ productId, currentPrice }) {
  const [signal, setSignal] = useState(null)

  useEffect(() => {
    if (!productId) return
    // Get price history to determine signal
    client.get(`/api/v1/collections/price-history/${productId}/`)
      .then(r => {
        const history = r.data.history || r.data || []
        if (history.length < 2) return

        const prices = history.map(h => parseFloat(h.price))
        const avg = prices.reduce((a, b) => a + b, 0) / prices.length
        const min = Math.min(...prices)
        const max = Math.max(...prices)

        if (currentPrice <= min) {
          setSignal({ text: 'Preço mínimo histórico', color: GREEN, icon: '🎯' })
        } else if (currentPrice < avg * 0.9) {
          setSignal({ text: 'Abaixo da média', color: GREEN, icon: '📉' })
        } else if (currentPrice >= max * 0.95) {
          setSignal({ text: 'Preço próximo do máximo', color: RED, icon: '⚠️' })
        } else if (currentPrice < avg) {
          setSignal({ text: 'Bom preço agora', color: BLUE, icon: '👍' })
        }
      })
      .catch(() => {})
  }, [productId, currentPrice])

  if (!signal) return null

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 8px', borderRadius: 6,
      background: `${signal.color}15`,
      border: `1px solid ${signal.color}30`,
    }}>
      <span style={{ fontSize: 11 }}>{signal.icon}</span>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: signal.color }}>
        {signal.text}
      </span>
    </div>
  )
}
