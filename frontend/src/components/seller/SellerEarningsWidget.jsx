/**
 * SellerEarningsWidget — Tier 4 daily-driver dashboard tile.
 *
 * Reads the existing /api/v1/payments/wallet/ + R7 dashboard endpoint
 * to produce a compact "today / week / month / next payout" widget.
 *
 * Loads in two passes:
 *   1. Wallet snapshot (cheap, single row)
 *   2. R7 dashboard window=7 for the week aggregate (heavier)
 *
 * Both gracefully degrade — one failing doesn't blank the other.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'
import FMT from '@/lib/format'


const ADMIN_BORDER = '#1A1A2E'
const ADMIN_CARD = '#111120'
const ADMIN_TEXT = '#E2E8F0'
const ADMIN_MUTED = '#64748B'
const ACCENT = '#22C55E'


export default function SellerEarningsWidget() {
  const [wallet, setWallet] = useState(null)
  const [week, setWeek] = useState(null)
  const [today, setToday] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false

    client.get('/api/v1/payments/wallet/').then((r) => {
      if (cancelled) return
      setWallet(r.data || {})
    }).catch(() => {})

    client.get('/api/v1/analytics/seller/dashboard/', { params: { days: 7 } })
      .then((r) => {
        if (cancelled) return
        setWeek(r.data?.totals || null)
        // Today = revenue[last]
        const arr = r.data?.revenue || []
        const last = arr[arr.length - 1]
        if (last) setToday(last)
      })
      .catch(() => {})

    return () => { cancelled = true }
  }, [])

  return (
    <div style={{
      background: ADMIN_CARD,
      border: `1px solid ${ADMIN_BORDER}`,
      borderRadius: 14, padding: 16,
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 14,
      }}>
        <h3 style={{
          margin: 0, fontSize: 13, fontWeight: 700,
          color: ADMIN_TEXT, textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}>
          Os teus ganhos
        </h3>
        <button
          type="button"
          onClick={() => navigate('/seller/wallet')}
          style={{
            background: 'transparent', color: '#A5B4FC',
            border: 'none', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
            fontFamily: 'inherit',
          }}
        >
          Ver carteira →
        </button>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12,
      }}>
        <Stat label="Saldo disponível"
              value={wallet ? FMT.currency(wallet.balance) : '—'}
              accent={ACCENT} primary />
        <Stat label="Pendente liberação"
              value={wallet ? FMT.currency(wallet.pending) : '—'}
              accent="#FBBF24" />
        <Stat label="Hoje"
              value={today ? FMT.currency(today.revenue) : '—'}
              sub={today ? `${today.orders} pedidos` : null} />
        <Stat label="Esta semana"
              value={week ? FMT.currency(week.gross_revenue) : '—'}
              sub={week ? `${week.order_count} pedidos` : null} />
      </div>

      {wallet?.next_payout_date && (
        <div style={{
          marginTop: 14, padding: '10px 12px',
          background: 'rgba(34, 197, 94, 0.08)',
          border: '1px solid rgba(34, 197, 94, 0.2)',
          borderRadius: 10,
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span aria-hidden="true" style={{ fontSize: 18 }}>💰</span>
          <div style={{ flex: 1, fontSize: 12, color: ADMIN_TEXT }}>
            Próximo pagamento: <strong style={{ color: ACCENT }}>
              {FMT.date(wallet.next_payout_date)}
            </strong>
          </div>
        </div>
      )}
    </div>
  )
}


function Stat({ label, value, sub, accent, primary }) {
  return (
    <div>
      <div style={{
        fontSize: 10, color: ADMIN_MUTED,
        textTransform: 'uppercase', letterSpacing: '0.05em',
        marginBottom: 4,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: primary ? 22 : 16,
        fontWeight: primary ? 700 : 600,
        color: accent || ADMIN_TEXT,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: ADMIN_MUTED, marginTop: 2 }}>
          {sub}
        </div>
      )}
    </div>
  )
}
