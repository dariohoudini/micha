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


// Keyed on the REAL backend Order.status machine:
//   confirmed (paid) → processing (seller confirms/prepares)
//   processing       → shipped
//   shipped          → delivered
// The previous map POSTed to /confirm/ /ship/ /deliver/ endpoints that
// never existed — the core seller fulfilment buttons all 404'd. The
// real endpoint is PATCH /orders/<id>/status/ {status}, which requires
// an Idempotency-Key so a network retry can't fire "shipped" events
// (buyer emails, carrier webhooks) twice.
const ACTIONS = {
  confirmed:  { label: 'Confirmar pedido',     to: 'processing', color: '#22C55E' },
  processing: { label: 'Marcar como expedido', to: 'shipped',    color: '#6366F1' },
  shipped:    { label: 'Marcar como entregue', to: 'delivered',  color: '#22C55E' },
}


export default function SellerOrderActionFlow({ order, onUpdated, compact = false }) {
  const [busy, setBusy] = useState(false)
  const action = order ? ACTIONS[order.status] : null

  if (!action) return null

  const handle = async () => {
    setBusy(true)
    try {
      const { data } = await client.patch(
        `/api/v1/orders/${order.id}/status/`,
        { status: action.to },
        { headers: { 'Idempotency-Key': `order-${order.id}-${action.to}` } },
      )
      haptic.medium()
      toast.success(action.label)
      track('order_action', {
        order_id: order.id, action: action.to,
      })
      onUpdated?.(data?.id ? data : { ...order, status: action.to })
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


export { ACTIONS }
