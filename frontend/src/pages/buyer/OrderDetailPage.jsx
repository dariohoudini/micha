import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import { useOrder } from '@/hooks/useQueries'
import client from '@/api/client'

const TRACKING_ICONS = {
  pending:         'M12 6v6l4 2',                                                      // clock
  confirmed:       'M20 6L9 17l-5-5',                                                  // check
  processing:      'M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83', // sun
  shipped:         'M5 8h14M5 8a2 2 0 1 0 0-4h14a2 2 0 1 0 0 4M5 8l1 12h12L19 8',     // box
  in_transit:      'M3 17h18M5 17V9l3-3h8l3 3v8',                                      // truck-ish
  out_for_delivery:'M3 9l9-6 9 6M3 9v12h6V14h6v7h6V9',                                 // truck delivery (house+arrow vibe)
  arrived:         'M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z',                   // pin
  delivered:       'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 0 0 1 1h3m10-11l2 2m-2-2v10a1 1 0 0 0-1 1h-3', // home
  completed:       'M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4l-10 10-3-3',               // double-check
  cancelled:       'M18 6L6 18M6 6l12 12',
  refunded:        'M3 12a9 9 0 1 0 9-9M3 12l3-3M3 12l3 3',
  update:          'M12 6v6l4 2',
}
const TRACKING_LABELS = {
  pending: 'Pedido recebido',
  confirmed: 'Confirmado pelo vendedor',
  processing: 'Em preparação',
  shipped: 'Enviado',
  in_transit: 'Em trânsito',
  out_for_delivery: 'Saiu para entrega',
  arrived: 'Chegou ao destino',
  delivered: 'Entregue',
  completed: 'Concluído',
  cancelled: 'Cancelado',
  refunded: 'Reembolsado',
  update: 'Atualização',
}

function fmtRelative(date) {
  const d = new Date(date)
  return d.toLocaleString('pt-AO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function TrackingTimeline({ events = [], status }) {
  if (!events.length) return null
  // Show newest first (server returns oldest-first, so reverse)
  const ordered = [...events].reverse()
  const current = ordered[0]
  const isError = status === 'cancelled' || status === 'refunded'

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {ordered.map((ev, i) => {
        const first = i === 0
        const iconPath = TRACKING_ICONS[ev.code] || TRACKING_ICONS.update
        const label = ev.description || TRACKING_LABELS[ev.code] || ev.code
        const dotColor = first ? (isError ? '#ef4444' : '#C9A84C') : '#2A2A2A'
        const lineColor = first && isError ? '#ef4444' : (first ? '#C9A84C' : '#2A2A2A')
        return (
          <div key={ev.id || i} style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 34 }}>
              <div style={{
                width: 34, height: 34, borderRadius: '50%',
                background: first ? (isError ? 'rgba(239,68,68,0.15)' : 'rgba(201,168,76,0.15)') : '#1E1E1E',
                border: `2px solid ${dotColor}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: first ? `0 0 0 4px ${isError ? 'rgba(239,68,68,0.12)' : 'rgba(201,168,76,0.12)'}` : 'none',
                flexShrink: 0,
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={first ? (isError ? '#ef4444' : '#C9A84C') : '#9A9A9A'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d={iconPath} />
                </svg>
              </div>
              {i < ordered.length - 1 && (
                <div style={{ flex: 1, width: 2, background: lineColor, margin: '4px 0', minHeight: 16 }} />
              )}
            </div>
            <div style={{ paddingTop: 6, paddingBottom: i < ordered.length - 1 ? 16 : 0, flex: 1 }}>
              <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, fontWeight: first ? 700 : 500, color: first ? '#FFF' : '#CCC', marginBottom: 2 }}>
                {label}
              </p>
              {ev.location && (
                <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: '#9A9A9A' }}>📍 {ev.location}</p>
              )}
              {ev.occurred_at && (
                <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: first ? '#C9A84C' : '#9A9A9A', marginTop: 2 }}>
                  {fmtRelative(ev.occurred_at)}
                </p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'

const STATUS_STEPS = [
  { key: 'pending',   label: 'Pedido recebido',     icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2' },
  { key: 'confirmed', label: 'Confirmado',           icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
  { key: 'shipped',   label: 'Em trânsito',          icon: 'M5 8h14M5 8a2 2 0 1 0 0-4h14a2 2 0 1 0 0 4M5 8l1 12h12L19 8' },
  { key: 'delivered', label: 'Entregue',             icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 0 0 1 1h3m10-11l2 2m-2-2v10a1 1 0 0 0-1 1h-3m-6 0a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h4' },
]
const CANCELLED_STEPS = ['pending', 'cancelled']
const ORDER_IDX = { pending: 0, confirmed: 1, shipped: 2, delivered: 3, cancelled: -1 }

function OrderTimeline({ status, timestamps = {} }) {
  const isCancelled = status === 'cancelled'
  const steps = isCancelled ? CANCELLED_STEPS : STATUS_STEPS.map(s => s.key)
  const currentIdx = isCancelled ? 1 : (ORDER_IDX[status] ?? 0)

  if (isCancelled) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {['pending', 'cancelled'].map((s, i) => (
          <div key={s} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
              <div style={{ width: 32, height: 32, borderRadius: '50%', background: i === 1 ? 'rgba(239,68,68,0.15)' : 'rgba(201,168,76,0.15)', border: `2px solid ${i === 1 ? '#ef4444' : '#C9A84C'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={i === 1 ? '#ef4444' : '#C9A84C'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {i === 1 ? <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></> : <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />}
                </svg>
              </div>
              {i === 0 && <div style={{ width: 2, height: 28, background: '#2A2A2A', margin: '3px 0' }} />}
            </div>
            <div style={{ paddingTop: 6 }}>
              <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, fontWeight: 600, color: i === 1 ? '#ef4444' : '#FFF' }}>{i === 0 ? 'Pedido recebido' : 'Cancelado'}</p>
              {timestamps[s] && <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{timestamps[s]}</p>}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {STATUS_STEPS.map((step, i) => {
        const done = i <= currentIdx
        const active = i === currentIdx
        return (
          <div key={step.key} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{ width: 34, height: 34, borderRadius: '50%', background: done ? 'rgba(201,168,76,0.15)' : '#1E1E1E', border: `2px solid ${done ? '#C9A84C' : '#2A2A2A'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.4s', boxShadow: active ? '0 0 0 4px rgba(201,168,76,0.15)' : 'none' }}>
                {done
                  ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={step.icon} /></svg>
                }
              </div>
              {i < STATUS_STEPS.length - 1 && (
                <div style={{ width: 2, height: 32, background: done && i < currentIdx ? '#C9A84C' : '#2A2A2A', margin: '4px 0', transition: 'background 0.4s' }} />
              )}
            </div>
            <div style={{ paddingTop: 7, paddingBottom: i < STATUS_STEPS.length - 1 ? 0 : 0 }}>
              <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, fontWeight: active ? 700 : done ? 500 : 400, color: done ? '#FFF' : '#9A9A9A' }}>{step.label}</p>
              {timestamps[step.key] && <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: '#C9A84C', marginTop: 2 }}>{timestamps[step.key]}</p>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const LIVE_STATUSES = ['pending', 'confirmed', 'shipped']

export default function OrderDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: order, isLoading, refetch } = useOrder(id)
  const [tracking, setTracking] = useState(null)

  const loadTracking = useCallback(() => {
    if (!id) return
    client.get(`/api/v1/orders/${id}/tracking/`)
      .then(r => setTracking(r.data))
      .catch(() => {})
  }, [id])

  useEffect(() => { loadTracking() }, [loadTracking])

  // Auto-poll while order is in-flight
  useEffect(() => {
    if (!order) return
    if (!LIVE_STATUSES.includes(order.status)) return
    const handle = setInterval(loadTracking, 30000)
    return () => clearInterval(handle)
  }, [order?.status, loadTracking])

  // Live polling while order is in-progress
  useEffect(() => {
    if (!order?.status || !LIVE_STATUSES.includes(order.status)) return
    const interval = setInterval(() => refetch(), 30_000)
    return () => clearInterval(interval)
  }, [order?.status, refetch])

  const S = { fontFamily: "'DM Sans',sans-serif" }

  if (isLoading) {
    return (
      <BuyerLayout>
        <div style={{ padding: '52px 16px 0', display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexShrink: 0 }}>
          <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 8 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div className="skeleton" style={{ width: 160, height: 18, borderRadius: 8 }} />
            <div className="skeleton" style={{ width: 90, height: 12, borderRadius: 6 }} />
          </div>
        </div>
        <div className="screen" style={{ flex: 1 }}>
          <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[120, 180, 100, 100].map((h, i) => (
              <div key={i} className="skeleton" style={{ height: h, borderRadius: 16 }} />
            ))}
          </div>
        </div>
      </BuyerLayout>
    )
  }

  if (!order) {
    return (
      <BuyerLayout>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '70%', gap: 16, padding: '0 32px', textAlign: 'center' }}>
          <p style={{ ...S, fontSize: 16, color: '#9A9A9A' }}>Pedido não encontrado.</p>
          <button onClick={() => navigate('/orders')} style={{ padding: '10px 24px', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>Ver pedidos</button>
        </div>
      </BuyerLayout>
    )
  }

  const items = order.items || order.order_items || []
  const delivery = order.delivery_fee || order.shipping_cost || 0
  const total = order.total || order.total_amount || 0
  const addr = order.delivery_address_obj || order.shipping_address || {}
  const timestamps = {
    pending:   order.created_at   ? new Date(order.created_at).toLocaleString('pt-AO') : null,
    confirmed: order.confirmed_at ? new Date(order.confirmed_at).toLocaleString('pt-AO') : null,
    shipped:   order.shipped_at   ? new Date(order.shipped_at).toLocaleString('pt-AO') : null,
    delivered: order.delivered_at ? new Date(order.delivered_at).toLocaleString('pt-AO') : null,
    cancelled: order.cancelled_at ? new Date(order.cancelled_at).toLocaleString('pt-AO') : null,
  }

  return (
    <BuyerLayout>
      <div style={{ padding: 'max(52px,env(safe-area-inset-top)) 16px 0', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button onClick={() => navigate('/orders')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <div>
          <h1 style={{ fontFamily: "'Playfair Display',serif", fontSize: 20, fontWeight: 700, color: '#FFF' }}>Detalhe do pedido</h1>
          <p style={{ ...S, fontSize: 12, color: '#C9A84C', marginTop: 2 }}>{order.order_number || order.id}</p>
        </div>
        {LIVE_STATUSES.includes(order.status) && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#059669', animation: 'pulseDot 2s infinite' }} />
            <span style={{ ...S, fontSize: 11, color: '#059669' }}>A actualizar</span>
          </div>
        )}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Timeline */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFF' }}>Rastreio do pedido</h3>
              {tracking?.tracking_number && (
                <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>#{tracking.tracking_number}</span>
              )}
            </div>
            {tracking?.events?.length > 0
              ? <TrackingTimeline events={tracking.events} status={order.status} />
              : <OrderTimeline status={order.status} timestamps={timestamps} />}
          </div>

          {/* Items */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid #1E1E1E' }}>
              <h3 style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFF' }}>Produtos ({items.length})</h3>
            </div>
            {items.map((item, i) => {
              const prod = item.product || item
              const price = Number(item.unit_price || item.price || prod.price || 0)
              const qty = item.quantity || 1
              return (
                <div key={item.id} style={{ display: 'flex', gap: 12, padding: 14, borderBottom: i < items.length - 1 ? '1px solid #1E1E1E' : 'none' }}>
                  <div style={{ width: 56, height: 56, borderRadius: 10, background: prod.image_color || '#1E1E1E', flexShrink: 0, overflow: 'hidden' }}>
                    {prod.image_url && <img src={prod.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ ...S, fontSize: 13, fontWeight: 500, color: '#FFF', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{prod.name}</p>
                    <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 4 }}>{prod.store_name || prod.seller}</p>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>×{qty}</span>
                      <span style={{ ...S, fontSize: 13, fontWeight: 600, color: '#C9A84C' }}>{fmt(price * qty)}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Delivery address */}
          {(addr.full_name || order.delivery_address) && (
            <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
              <h3 style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Endereço de entrega</h3>
              <p style={{ ...S, fontSize: 14, fontWeight: 500, color: '#FFF' }}>{addr.full_name}</p>
              {addr.phone && <p style={{ ...S, fontSize: 13, color: '#9A9A9A', marginTop: 2 }}>{addr.phone}</p>}
              <p style={{ ...S, fontSize: 13, color: '#9A9A9A', marginTop: 2 }}>
                {[addr.street, addr.neighbourhood, addr.municipality, addr.province || order.delivery_province].filter(Boolean).join(', ')
                  || order.delivery_address}
              </p>
            </div>
          )}

          {/* Payment summary */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
            <h3 style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Resumo</h3>
            {[
              { label: 'Subtotal', value: fmt(total - delivery) },
              { label: 'Entrega', value: delivery === 0 ? 'Grátis' : fmt(delivery), green: delivery === 0 },
              { label: 'Método', value: order.payment_method === 'multicaixa' ? 'Multicaixa Express' : order.payment_method || '—' },
            ].map(row => (
              <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>{row.label}</span>
                <span style={{ ...S, fontSize: 13, color: row.green ? '#059669' : '#FFF' }}>{row.value}</span>
              </div>
            ))}
            <div style={{ height: 1, background: '#2A2A2A', margin: '10px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFF' }}>Total pago</span>
              <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>{fmt(total)}</span>
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 10 }}>
            {order.status !== 'delivered' && order.status !== 'cancelled' && (
              <button onClick={() => navigate('/chat')} style={{ flex: 1, padding: '13px 0', borderRadius: 14, border: '1px solid #2A2A2A', background: '#141414', ...S, fontSize: 14, fontWeight: 600, color: '#FFF', cursor: 'pointer' }}>
                Suporte
              </button>
            )}
            {order.status === 'delivered' && (
              <button onClick={() => navigate(`/product/${items[0]?.product?.id || items[0]?.id}`)} style={{ flex: 1, padding: '13px 0', borderRadius: 14, border: 'none', background: '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                Avaliar produtos
              </button>
            )}
            {(order.status === 'delivered' || order.status === 'shipped') && !order.has_dispute && (
              <button onClick={() => navigate(`/dispute/${order.id}`)} style={{ flex: 1, padding: '13px 0', borderRadius: 14, border: '1px solid rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.08)', ...S, fontSize: 14, fontWeight: 600, color: '#f59e0b', cursor: 'pointer' }}>
                Disputar
              </button>
            )}
            {order.status === 'pending' && (
              <button onClick={async () => {
                try {
                  await client.post(`/api/v1/orders/${order.id}/cancel/`, { reason: 'Cancelado pelo comprador' })
                  navigate('/orders')
                } catch {}
              }} style={{ flex: 1, padding: '13px 0', borderRadius: 14, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.08)', ...S, fontSize: 14, fontWeight: 600, color: '#ef4444', cursor: 'pointer' }}>
                Cancelar pedido
              </button>
            )}
          </div>
        </div>
      </div>
    </BuyerLayout>
  )
}
