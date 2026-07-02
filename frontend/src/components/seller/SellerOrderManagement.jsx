import client from '@/api/client'
/**
 * MICHA Express — Seller Order Management UX
 * Covers improvements: 32 (Pending actions alert), 44 (Kanban board),
 * 45 (Packing slip), 46 (Batch confirm), 47 (Add tracking number)
 */
import { useState } from 'react'
import { asList } from '@/lib/asList'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

const STATUS_COLORS = {
  pending: { bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.3)', text: '#F59E0B', label: 'Novo' },
  confirmed: { bg: 'rgba(59,130,246,0.1)', border: 'rgba(59,130,246,0.3)', text: '#3B82F6', label: 'Confirmado' },
  processing: { bg: 'rgba(139,92,246,0.1)', border: 'rgba(139,92,246,0.3)', text: '#8B5CF6', label: 'Em preparo' },
  shipped: { bg: 'rgba(5,150,105,0.1)', border: 'rgba(5,150,105,0.3)', text: '#059669', label: 'Enviado' },
}


const fmt = (n) => n.toLocaleString('pt-AO') + ' Kz'

// ─── Pending Actions Alert Bar ──────────────────────────────────────────────
export function PendingActionsBar({ orders }) {
  const pending = orders.filter(o => o.status === 'pending').length
  const disputes = 1
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || (pending === 0 && disputes === 0)) return null

  return (
    <div style={{
      margin: '0 16px 16px', background: 'rgba(239,68,68,0.08)',
      border: '1.5px solid rgba(239,68,68,0.3)', borderRadius: 12, padding: '12px 14px',
      display: 'flex', alignItems: 'center', gap: 10
    }}>
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#EF4444', flexShrink: 0, animation: 'pulse 1.5s infinite' }} />
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
      <div style={{ flex: 1 }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#EF4444', margin: 0 }}>
          Acção necessária
        </p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '2px 0 0' }}>
          {pending > 0 && `${pending} pedido${pending > 1 ? 's' : ''} aguardando confirmação`}
          {pending > 0 && disputes > 0 && ' · '}
          {disputes > 0 && `${disputes} disputa aberta`}
        </p>
      </div>
      <button onClick={() => setDismissed(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="2" strokeLinecap="round">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  )
}

// ─── Order Card ──────────────────────────────────────────────────────────────
function OrderCard({ order, onConfirm, onTrack, onPrint, selected, onSelect }) {
  const [trackingOpen, setTrackingOpen] = useState(false)
  const [tracking, setTracking] = useState('')
  const sc = STATUS_COLORS[order.status]

  return (
    <div style={{
      background: CARD, border: `1.5px solid ${selected ? GOLD : BORDER}`,
      borderRadius: 14, padding: 14, marginBottom: 10, transition: 'all 0.2s'
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
        {/* Batch select checkbox */}
        <button onClick={() => onSelect(order.id)} style={{
          width: 18, height: 18, borderRadius: 5, border: `2px solid ${selected ? GOLD : BORDER}`,
          background: selected ? GOLD : 'none', cursor: 'pointer', flexShrink: 0, marginTop: 2,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          {selected && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="3" strokeLinecap="round"><polyline points="20 6 9 17 4 12" /></svg>}
        </button>

        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: TEXT }}>{order.id}</span>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED }}>{order.time}</span>
          </div>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '0 0 4px' }}>{order.buyer} · {order.province}</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: TEXT, margin: 0 }}>{order.items}</p>
        </div>

        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 14, fontWeight: 700, color: GOLD }}>{fmt(order.total)}</span>
          <div style={{ marginTop: 4, padding: '2px 8px', borderRadius: 6, background: sc.bg, border: `1px solid ${sc.border}`, display: 'inline-block' }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: sc.text }}>{sc.label}</span>
          </div>
        </div>
      </div>

      {/* Buyer notes */}
      {order.notes && (
        <div style={{ background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 8, padding: '8px 10px', marginBottom: 10 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD, margin: 0 }}>
            Nota do comprador: <span style={{ color: TEXT }}>{order.notes}</span>
          </p>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8 }}>
        {order.status === 'pending' && (
          <button onClick={() => onConfirm(order.id)} style={{
            flex: 1, padding: '9px 12px', borderRadius: 10, border: 'none', cursor: 'pointer',
            background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600
          }}>Confirmar</button>
        )}
        {order.status === 'confirmed' && (
          <button onClick={() => setTrackingOpen(true)} style={{
            flex: 1, padding: '9px 12px', borderRadius: 10, border: `1px solid #3B82F6`, cursor: 'pointer',
            background: 'rgba(59,130,246,0.1)', color: '#3B82F6', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600
          }}>Adicionar rastreamento</button>
        )}
        <button onClick={() => onPrint(order)} style={{
          padding: '9px 12px', borderRadius: 10, border: `1px solid ${BORDER}`, cursor: 'pointer',
          background: 'none', color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <polyline points="6 9 6 2 18 2 18 9" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" />
          </svg>
        </button>
      </div>

      {/* Tracking input */}
      {trackingOpen && (
        <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
          <input
            value={tracking}
            onChange={e => setTracking(e.target.value)}
            placeholder="Número de rastreamento..."
            style={{
              flex: 1, padding: '9px 12px', background: BG, border: `1px solid ${BORDER}`,
              borderRadius: 10, color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 12, outline: 'none'
            }}
          />
          <button onClick={() => { onTrack(order.id, tracking); setTrackingOpen(false) }} style={{
            padding: '9px 14px', borderRadius: 10, border: 'none', cursor: 'pointer',
            background: '#059669', color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600
          }}>Enviar</button>
        </div>
      )}
    </div>
  )
}

// ─── Kanban Board ────────────────────────────────────────────────────────────
export function OrderKanban() {
  const [orders, setOrders] = useState([])
  useEffect(() => {
    client.get('/api/v1/orders/seller/').then(r => {
      setOrders(asList(r.data))
    }).catch(() => setOrders([]))
  }, [])
  const [selected, setSelected] = useState([])
  const [activeCol, setActiveCol] = useState('pending')

  const columns = ['pending', 'confirmed', 'processing', 'shipped']
  const colOrders = orders.filter(o => o.status === activeCol)

  const confirm = (id) => setOrders(prev => prev.map(o => o.id === id ? { ...o, status: 'confirmed' } : o))
  const track = (id, num) => setOrders(prev => prev.map(o => o.id === id ? { ...o, status: 'shipped', tracking: num } : o))
  const toggleSelect = (id) => setSelected(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id])
  const batchConfirm = () => {
    setOrders(prev => prev.map(o => selected.includes(o.id) && o.status === 'pending' ? { ...o, status: 'confirmed' } : o))
    setSelected([])
  }
  const print = (order) => {
    const w = window.open('', '_blank')
    w.document.write(`
      <html><body style="font-family:sans-serif;padding:20px;">
        <h2>MICHA Express — Guia de entrega</h2>
        <p><strong>Pedido:</strong> ${order.id}</p>
        <p><strong>Comprador:</strong> ${order.buyer}</p>
        <p><strong>Provincia:</strong> ${order.province}</p>
        <p><strong>Artigos:</strong> ${order.items}</p>
        <p><strong>Total:</strong> ${fmt(order.total)}</p>
        ${order.notes ? `<p><strong>Nota:</strong> ${order.notes}</p>` : ''}
      </body></html>
    `)
    w.print()
  }

  return (
    <div style={{ background: BG, minHeight: '100vh', paddingBottom: 40 }}>
      <div style={{ maxWidth: 480, margin: '0 auto' }}>

        {/* Header */}
        <div style={{ padding: '40px 16px 0' }}>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, color: TEXT, margin: '0 0 4px' }}>Pedidos</h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: 0 }}>Seller order management demo</p>
        </div>

        <div style={{ padding: '16px 0' }}>
          <PendingActionsBar orders={orders} />

          {/* Column tabs */}
          <div style={{ display: 'flex', padding: '0 16px', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
            {(columns || []).map(col => {
              const count = orders.filter(o => o.status === col).length
              const sc = STATUS_COLORS[col]
              return (
                <button key={col} onClick={() => setActiveCol(col)} style={{
                  padding: '7px 12px', borderRadius: 10, border: `1.5px solid ${activeCol === col ? sc.text : BORDER}`,
                  background: activeCol === col ? sc.bg : 'none',
                  color: activeCol === col ? sc.text : MUTED,
                  fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600,
                  cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
                  display: 'flex', alignItems: 'center', gap: 6
                }}>
                  {sc.label}
                  {count > 0 && (
                    <span style={{
                      background: activeCol === col ? sc.text : BORDER,
                      color: activeCol === col ? '#000' : MUTED,
                      borderRadius: 10, padding: '0 6px', fontSize: 10, fontWeight: 700
                    }}>{count}</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Batch confirm bar */}
          {selected.length > 0 && (
            <div style={{ margin: '12px 16px 0', background: 'rgba(201,168,76,0.08)', border: `1px solid rgba(201,168,76,0.2)`, borderRadius: 10, padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: GOLD }}>{selected.length} seleccionado{selected.length > 1 ? 's' : ''}</span>
              <button onClick={batchConfirm} style={{ padding: '7px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600 }}>
                Confirmar todos
              </button>
            </div>
          )}

          {/* Orders */}
          <div style={{ padding: '12px 16px 0' }}>
            {colOrders.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 0', color: MUTED }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14 }}>Sem pedidos nesta categoria</p>
              </div>
            ) : (
              (colOrders || []).map(order => (
                <OrderCard
                  key={order.id}
                  order={order}
                  onConfirm={confirm}
                  onTrack={track}
                  onPrint={print}
                  selected={selected.includes(order.id)}
                  onSelect={toggleSelect}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default OrderKanban
