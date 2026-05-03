import { useState, useEffect } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444', BLUE = '#3B82F6'
const fmt = (n) => Number(n||0).toLocaleString('pt-AO') + ' Kz'
const STATUS_COLORS = { pending: G, confirmed: BLUE, processing: BLUE, shipped: BLUE, delivered: GREEN, completed: GREEN, cancelled: RED, refunded: RED }

export default function AdminOrdersPage() {
  const [orders, setOrders] = useState([])
  const [disputes, setDisputes] = useState([])
  const [payouts, setPayouts] = useState([])
  const [tab, setTab] = useState('disputes')
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      client.get('/api/v1/admin-api/orders/'),
      client.get('/api/v1/disputes/admin/'),
      client.get('/api/v1/payments/payout/admin/'),
    ]).then(([ordersRes, disputesRes, payoutsRes]) => {
      if (ordersRes.status === 'fulfilled') setOrders(ordersRes.value.data.results || ordersRes.value.data || [])
      if (disputesRes.status === 'fulfilled') setDisputes(disputesRes.value.data.results || disputesRes.value.data || [])
      if (payoutsRes.status === 'fulfilled') setPayouts(payoutsRes.value.data.results || payoutsRes.value.data || [])
    }).finally(() => setLoading(false))
  }, [])

  const resolveDispute = async (id, resolution) => {
    try {
      await client.post(`/api/v1/disputes/admin/${id}/resolve/`, { resolution })
      setDisputes(prev => prev.map(d => d.id === id ? { ...d, status: 'resolved', resolution } : d))
      showToast('Disputa resolvida')
    } catch { showToast('Erro ao resolver', 'error') }
  }

  const approvePayout = async (id) => {
    try {
      await client.post(`/api/v1/payments/payout/admin/${id}/`, { action: 'approve' })
      setPayouts(prev => prev.map(p => p.id === id ? { ...p, status: 'approved' } : p))
      showToast('Pagamento aprovado')
    } catch { showToast('Erro ao aprovar', 'error') }
  }

  const pendingDisputes = disputes.filter(d => d.status === 'open' || d.status === 'investigating')
  const pendingPayouts = payouts.filter(p => p.status === 'pending')

  return (
    <AdminLayout title="Pedidos">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, fontFamily: "'DM Sans'", fontSize: 13 }}>{toast.msg}</div>}

        <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 16px' }}>Pedidos & Disputas</h1>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, overflowX: 'auto' }}>
          {[
            { key: 'disputes', label: `Disputas (${pendingDisputes.length})` },
            { key: 'payouts', label: `Pagamentos (${pendingPayouts.length})` },
            { key: 'orders', label: `Todos os pedidos` },
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{ padding: '8px 14px', borderRadius: 10, border: `1.5px solid ${tab === t.key ? G : BORDER}`, background: tab === t.key ? 'rgba(201,168,76,0.1)' : 'none', color: tab === t.key ? G : MUTED, fontFamily: "'DM Sans'", fontSize: 12, fontWeight: tab === t.key ? 600 : 400, cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Disputes */}
        {tab === 'disputes' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED }}>A carregar...</p> :
              disputes.length === 0 ? <p style={{ fontFamily: "'DM Sans'", color: GREEN, fontSize: 14, textAlign: 'center', padding: 40 }}>✅ Sem disputas abertas</p> :
              disputes.map(d => (
                <div key={d.id} style={{ background: CARD, borderRadius: 14, border: `1.5px solid ${d.status === 'open' ? 'rgba(239,68,68,0.3)' : BORDER}`, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: TEXT, margin: '0 0 2px' }}>Disputa #{String(d.id).slice(0,8)}</p>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: 0 }}>{d.buyer_email} vs {d.seller_email}</p>
                    </div>
                    <span style={{ padding: '3px 10px', borderRadius: 6, background: d.status === 'open' ? 'rgba(239,68,68,0.15)' : 'rgba(5,150,105,0.15)', color: d.status === 'open' ? RED : GREEN, fontFamily: "'DM Sans'", fontSize: 11, fontWeight: 600 }}>
                      {d.status}
                    </span>
                  </div>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 13, color: MUTED, margin: '0 0 12px', lineHeight: 1.5 }}>{d.reason || d.description}</p>
                  <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: '0 0 12px' }}>Valor em disputa: <strong style={{ color: G }}>{fmt(d.order_total)}</strong></p>
                  {(d.status === 'open' || d.status === 'investigating') && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => resolveDispute(d.id, 'buyer_wins')} style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: BLUE, color: '#fff', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                        🏆 Reembolsar comprador
                      </button>
                      <button onClick={() => resolveDispute(d.id, 'seller_wins')} style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: G, color: '#000', fontFamily: "'DM Sans'", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                        💰 Pagar vendedor
                      </button>
                    </div>
                  )}
                </div>
              ))
            }
          </div>
        )}

        {/* Payouts */}
        {tab === 'payouts' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED }}>A carregar...</p> :
              payouts.length === 0 ? <p style={{ fontFamily: "'DM Sans'", color: GREEN, fontSize: 14, textAlign: 'center', padding: 40 }}>✅ Sem pagamentos pendentes</p> :
              payouts.map(p => (
                <div key={p.id} style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, color: TEXT, margin: '0 0 2px' }}>{p.seller_email}</p>
                      <p style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, margin: 0 }}>{p.bank_name} · {p.account_number}</p>
                    </div>
                    <p style={{ fontFamily: "'Playfair Display'", fontSize: 18, fontWeight: 700, color: G, margin: 0 }}>{fmt(p.amount)}</p>
                  </div>
                  {p.status === 'pending' && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => approvePayout(p.id)} style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: GREEN, color: '#fff', fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                        ✅ Aprovar pagamento
                      </button>
                      <button onClick={() => { client.post(`/api/v1/payments/payout/admin/${p.id}/`, { action: 'reject' }).then(() => { setPayouts(prev => prev.filter(x => x.id !== p.id)); showToast('Pagamento rejeitado') }).catch(() => showToast('Erro', 'error')) }} style={{ padding: '10px 14px', borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: RED, fontFamily: "'DM Sans'", fontSize: 13, cursor: 'pointer' }}>
                        ❌
                      </button>
                    </div>
                  )}
                </div>
              ))
            }
          </div>
        )}

        {/* All orders */}
        {tab === 'orders' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {loading ? <p style={{ fontFamily: "'DM Sans'", color: MUTED }}>A carregar...</p> :
              orders.map(o => (
                <div key={o.id} style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: '13px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 13, fontWeight: 500, color: TEXT, margin: '0 0 2px' }}>#{String(o.id).slice(0,8).toUpperCase()}</p>
                    <p style={{ fontFamily: "'DM Sans'", fontSize: 11, color: MUTED, margin: 0 }}>{o.buyer_email} · {new Date(o.created_at).toLocaleDateString('pt-AO')}</p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontFamily: "'Playfair Display'", fontSize: 14, fontWeight: 700, color: G, margin: '0 0 2px' }}>{fmt(o.total)}</p>
                    <span style={{ padding: '2px 8px', borderRadius: 4, background: `${STATUS_COLORS[o.status] || MUTED}20`, color: STATUS_COLORS[o.status] || MUTED, fontFamily: "'DM Sans'", fontSize: 10, fontWeight: 600 }}>{o.status}</span>
                  </div>
                </div>
              ))
            }
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
