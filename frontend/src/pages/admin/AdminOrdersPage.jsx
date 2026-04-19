import { useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import { formatPrice } from '@/components/buyer/mockData'

const MOCK_ORDERS = [
  { id: 'ORD-2847', buyer: 'João Silva', seller: 'Moda Luanda', product: 'Vestido Capulana ×2', total: 17000, commission: 850, status: 'delivered', date: '13 Abr 09:32', province: 'Luanda', dispute: false },
  { id: 'ORD-2801', buyer: 'Maria Santos', seller: 'Beauty Angola', product: 'Kit Skincare Natural', total: 18500, commission: 925, status: 'dispute', date: '12 Abr 11:15', province: 'Benguela', dispute: true, disputeReason: 'Produto não corresponde à descrição' },
  { id: 'ORD-2798', buyer: 'Pedro Neto', seller: 'TechShop Angola', product: 'Auriculares Bluetooth', total: 22000, commission: 1100, status: 'shipped', date: '12 Abr 08:00', province: 'Luanda', dispute: false },
  { id: 'ORD-2756', buyer: 'Ana Costa', seller: 'SportZone AO', product: 'Ténis Nike Air Max', total: 52000, commission: 2600, status: 'dispute', date: '10 Abr 14:20', province: 'Huambo', dispute: true, disputeReason: 'Produto chegou danificado' },
  { id: 'ORD-2701', buyer: 'Carlos Mendes', seller: 'Casa & Lar AO', product: 'Conjunto Panelas', total: 32000, commission: 1600, status: 'cancelled', date: '08 Abr 16:45', province: 'Luanda', dispute: false },
  { id: 'ORD-2689', buyer: 'Lucia Ferreira', seller: 'Moda Luanda', product: 'Bolsa de Couro', total: 28000, commission: 1400, status: 'delivered', date: '07 Abr 10:30', province: 'Luanda', dispute: false },
]

const STATUS_CONFIG = {
  pending:   { label: 'Pendente',   color: '#f59e0b' },
  confirmed: { label: 'Confirmado', color: '#3b82f6' },
  shipped:   { label: 'Enviado',   color: '#8b5cf6' },
  delivered: { label: 'Entregue',  color: '#10b981' },
  cancelled: { label: 'Cancelado', color: '#6b7280' },
  dispute:   { label: 'Disputa',   color: '#ef4444' },
}

export default function AdminOrdersPage() {
  const [orders, setOrders] = useState(MOCK_ORDERS)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const resolveDispute = (id, favour) => {
    setOrders(prev => prev.map(o => o.id === id ? { ...o, status: favour === 'buyer' ? 'cancelled' : 'delivered', dispute: false } : o))
    showToast(`Disputa resolvida a favor do ${favour === 'buyer' ? 'comprador' : 'vendedor'}.`)
    setSelected(null)
  }

  const filtered = orders.filter(o => {
    const matchFilter = filter === 'all' || o.status === filter
    const matchSearch = !search || o.id.toLowerCase().includes(search.toLowerCase()) || o.buyer.toLowerCase().includes(search.toLowerCase()) || o.seller.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  const totalRevenue = orders.filter(o => o.status === 'delivered').reduce((a, o) => a + o.total, 0)
  const totalCommission = orders.filter(o => o.status === 'delivered').reduce((a, o) => a + o.commission, 0)
  const disputeCount = orders.filter(o => o.dispute).length

  return (
    <AdminLayout title="Pedidos">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>{toast.msg}</div>
      )}

      {/* Dispute resolution modal */}
      {selected?.dispute && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) setSelected(null) }}>
          <div style={{ background: ADMIN_COLORS.card, borderRadius: '20px 20px 0 0', border: `1px solid ${ADMIN_COLORS.border}`, padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: ADMIN_COLORS.border, margin: '0 auto 20px' }} />
            <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 12, padding: '12px 14px', marginBottom: 16 }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: '#ef4444', marginBottom: 4 }}>⚠️ Disputa aberta</p>
              <p style={{ fontSize: 13, color: ADMIN_COLORS.text, marginBottom: 2 }}>{selected.id} · {formatPrice(selected.total)}</p>
              <p style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>Motivo: {selected.disputeReason}</p>
            </div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
              <div style={{ flex: 1, background: ADMIN_COLORS.surface, borderRadius: 10, padding: 10 }}>
                <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 2 }}>Comprador</p>
                <p style={{ fontSize: 13, color: ADMIN_COLORS.text, fontWeight: 500 }}>{selected.buyer}</p>
              </div>
              <div style={{ flex: 1, background: ADMIN_COLORS.surface, borderRadius: 10, padding: 10 }}>
                <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 2 }}>Vendedor</p>
                <p style={{ fontSize: 13, color: ADMIN_COLORS.text, fontWeight: 500 }}>{selected.seller}</p>
              </div>
            </div>
            <p style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 14, textAlign: 'center' }}>Resolver a favor de:</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button onClick={() => resolveDispute(selected.id, 'buyer')}
                style={{ padding: '14px', borderRadius: 12, border: 'none', background: '#6366f1', fontSize: 14, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
                🛒 Comprador — Reembolso total
              </button>
              <button onClick={() => resolveDispute(selected.id, 'seller')}
                style={{ padding: '14px', borderRadius: 12, border: '1px solid rgba(16,185,129,0.3)', background: 'rgba(16,185,129,0.1)', fontSize: 14, fontWeight: 600, color: '#10b981', cursor: 'pointer' }}>
                🏪 Vendedor — Manter pagamento
              </button>
              <button onClick={() => setSelected(null)}
                style={{ padding: '14px', borderRadius: 12, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 14, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {/* Revenue stats */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[
            { l: 'GMV total', v: formatPrice(totalRevenue), c: '#818cf8' },
            { l: 'Comissões', v: formatPrice(totalCommission), c: '#10b981' },
            { l: 'Disputas', v: disputeCount, c: '#ef4444' },
          ].map(s => (
            <div key={s.l} style={{ flex: 1, background: ADMIN_COLORS.card, borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, padding: '10px 8px', textAlign: 'center' }}>
              <p style={{ fontSize: 13, fontWeight: 700, color: s.c }}>{s.v}</p>
              <p style={{ fontSize: 9, color: ADMIN_COLORS.muted, marginTop: 1 }}>{s.l}</p>
            </div>
          ))}
        </div>

        {/* Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '10px 14px', marginBottom: 10 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar por ID, comprador ou vendedor..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: ADMIN_COLORS.text }} />
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {[{ v: 'all', l: 'Todos' }, { v: 'dispute', l: `Disputas (${disputeCount})` }, { v: 'delivered', l: 'Entregues' }, { v: 'shipped', l: 'Enviados' }, { v: 'cancelled', l: 'Cancelados' }].map(f => (
            <button key={f.v} onClick={() => setFilter(f.v)}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#6366f1' : ADMIN_COLORS.border}`, background: filter === f.v ? 'rgba(99,102,241,0.1)' : 'transparent', fontSize: 11, color: filter === f.v ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer', whiteSpace: 'nowrap' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(order => {
            const status = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending
            return (
              <div key={order.id} style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${order.dispute ? 'rgba(239,68,68,0.3)' : ADMIN_COLORS.border}`, padding: 14 }}>
                {order.dispute && <div style={{ height: 2, background: '#ef4444', borderRadius: '14px 14px 0 0', margin: '-14px -14px 14px' }} />}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#818cf8' }}>{order.id}</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: status.color, background: `${status.color}18`, padding: '3px 8px', borderRadius: 20 }}>{status.label}</span>
                </div>
                <p style={{ fontSize: 13, color: ADMIN_COLORS.text, marginBottom: 6 }}>{order.product}</p>
                <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>🛒 {order.buyer}</span>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>🏪 {order.seller}</span>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>📅 {order.date}</span>
                </div>
                {order.dispute && (
                  <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, padding: '8px 10px', marginBottom: 10 }}>
                    <p style={{ fontSize: 12, color: '#ef4444' }}>⚠️ {order.disputeReason}</p>
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10, borderTop: `1px solid ${ADMIN_COLORS.border}` }}>
                  <div>
                    <span style={{ fontSize: 15, fontWeight: 700, color: ADMIN_COLORS.text }}>{formatPrice(order.total)}</span>
                    <span style={{ fontSize: 11, color: '#10b981', marginLeft: 8 }}>+{formatPrice(order.commission)} comissão</span>
                  </div>
                  {order.dispute && (
                    <button onClick={() => setSelected(order)}
                      style={{ padding: '7px 14px', borderRadius: 10, border: 'none', background: '#ef4444', fontSize: 12, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
                      Resolver disputa
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </AdminLayout>
  )
}
