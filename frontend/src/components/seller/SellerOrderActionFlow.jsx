/**
 * SellerOrderActionFlow — Tier 4 single-CTA per state.
 *
 * Replaces the multi-button menu sellers had to navigate. At any
 * given order state, exactly ONE primary action makes sense:
 *
 *   pending / awaiting_seller  → "Confirmar pedido"
 *   confirmed / awaiting_ship  → "Marcar como expedido"
 *   shipped                    → "Marcar como entregue"
 *   delivered                  → (no action; awaiting buyer protection lapse)
 *   cancelled / refunded       → (no action)
 *
 * Each action fires the corresponding POST and surfaces:
 *   - Optimistic UI (the button locks, shows spinner)
 *   - Toast on success / error
 *   - Haptic feedback (medium on success)
 *
 * Where it lives
 * ──────────────
 * Drop into SellerOrdersPage row OR SellerOrderDetailPage as a
 * standalone CTA. Pure presentational — parent owns the order state.
 *
 * Props
 * ─────
 *   order        { id, status }
 *   onUpdated    (newOrderShape) => void  (parent refetches / patches)
 */
import { useState } from 'react'
import client from '@/api/client'
import { toast } from '@/components/ui/Toast'
import { haptic } from '@/hooks/useUX'
import { track } from '@/lib/events'


const ACTIONS = {
  pending:          { label: 'Confirmar pedido',     path: 'confirm',  color: '#22C55E' },
  awaiting_seller:  { label: 'Confirmar pedido',     path: 'confirm',  color: '#22C55E' },
  confirmed:        { label: 'Marcar como expedido', path: 'ship',     color: '#6366F1' },
  awaiting_ship:    { label: 'Marcar como expedido', path: 'ship',     color: '#6366F1' },
  shipped:          { label: 'Marcar como entregue', path: 'deliver',  color: '#22C55E' },
  in_transit:       { label: 'Marcar como entregue', path: 'deliver',  color: '#22C55E' },
}


export default function SellerOrderActionFlow({ order, onUpdated, compact = false }) {
  const [busy, setBusy] = useState(false)
  const action = order ? ACTIONS[order.status] : null

  if (!action) return null

  const handle = async () => {
    setBusy(true)
    try {
      const { data } = await client.post(
        `/api/v1/orders/${order.id}/${action.path}/`,
      )
      haptic.medium()
      toast.success(action.label)
      track('order_action', {
        order_id: order.id, action: action.path,
      })
      onUpdated?.(data || { ...order, status: nextStatus(order.status) })
    } catch (e) {
      haptic.error()
      toast.error(e?.response?.data?.detail || 'Falhou. Tenta de novo.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handle}
      disabled={busy}
      aria-busy={busy}
      style={{
        background: action.color, color: 'white',
        border: 'none',
        padding: compact ? '8px 14px' : '12px 20px',
        borderRadius: compact ? 8 : 12,
        fontSize: compact ? 12 : 14,
        fontWeight: 700, cursor: busy ? 'not-allowed' : 'pointer',
        opacity: busy ? 0.6 : 1,
        minHeight: compact ? 36 : 44,
        fontFamily: "'DM Sans', sans-serif",
        display: 'inline-flex', alignItems: 'center', gap: 6,
      }}
    >
      {busy && (
        <span
          aria-hidden="true"
          style={{
            width: 14, height: 14, borderRadius: '50%',
            border: '2px solid currentColor',
            borderTopColor: 'transparent',
            animation: 'oaf-spin 0.7s linear infinite',
          }}
        />
      )}
      <span>{busy ? 'A processar…' : action.label}</span>
      <style>{`
        @keyframes oaf-spin { to { transform: rotate(360deg); } }
      `}</style>
    </button>
  )
}


function nextStatus(current) {
  return ({
    pending: 'confirmed',
    awaiting_seller: 'confirmed',
    confirmed: 'shipped',
    awaiting_ship: 'shipped',
    shipped: 'delivered',
    in_transit: 'delivered',
  })[current] || current
}


export { ACTIONS }
