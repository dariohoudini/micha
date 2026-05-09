import { useState, useEffect, useCallback } from 'react'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'
import HelperBot from '@/components/shared/HelperBot'
import OrderKanban, { PendingActionsBar } from '@/components/seller/SellerOrderManagement'
import SellerCheckpointModal from '@/components/seller/SellerCheckpointModal'
import SellerReturnsList from '@/components/seller/SellerReturnsList'
import { haptic } from '@/hooks/useUX'


const STATUS_CONFIG = {
  pending:   { label: 'Pendente',   color: '#f59e0b' },
  confirmed: { label: 'Confirmado', color: '#3b82f6' },
  shipped:   { label: 'Enviado',    color: '#8b5cf6' },
  delivered: { label: 'Entregue',   color: '#059669' },
  cancelled: { label: 'Cancelado',  color: '#dc2626' },
}

export default function SellerOrdersPage() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [toast, setToast] = useState(null)
  const [checkpointOrderId, setCheckpointOrderId] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 2500) }

  const loadOrders = useCallback(async () => {
    if (filter === 'returns') { setLoading(false); return }  // returns view fetches its own
    setLoading(true)
    try {
      const params = filter !== 'all' ? `?status=${filter}` : ''
      const res = await client.get(`/api/v1/orders/seller/${params}`)
      setOrders(res.data.results || res.data || [])
    } catch { setOrders([]) }
    finally { setLoading(false) }
  }, [filter])

  useEffect(() => { loadOrders() }, [loadOrders])

  const updateStatus = async (orderId, status) => {
    try {
      await client.post(`/api/v1/orders/${orderId}/status/`, { status })
      setOrders(prev => prev.map(o => o.id === orderId ? { ...o, status } : o))
      showToast('Estado actualizado.')
    } catch { showToast('Erro ao actualizar.', 'error') }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <SellerLayout title="Gestão de Pedidos">
      {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#fff', padding: '10px 20px', borderRadius: 12, ...S, fontSize: 13, whiteSpace: 'nowrap' }}>{toast.msg}</div>}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 10 }}>
          {[{v:'all',l:'Todos'},{v:'pending',l:'Pendentes'},{v:'confirmed',l:'Confirmados'},{v:'shipped',l:'Enviados'},{v:'delivered',l:'Entregues'},{v:'returns',l:'↩️ Devoluções'}].map(f => (
            <button key={f.v} onClick={() => setFilter(f.v)}
              style={{ padding: '5px 12px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#C9A84C' : '#2A2A2A'}`, background: filter === f.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 11, color: filter === f.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {filter === 'returns' ? (
          <div style={{ padding: '0 16px 20px' }}>
            <SellerReturnsList />
          </div>
        ) : loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
          </div>
        ) : orders.length === 0 ? (
          <p style={{ ...S, fontSize: 14, color: '#9A9A9A', textAlign: 'center', padding: '60px 0' }}>Sem pedidos encontrados.</p>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {orders.map(order => {
              const status = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending
              return (
                <div key={order.id} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ ...S, fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>#{String(order.id).slice(-8).toUpperCase()}</span>
                    <span style={{ ...S, fontSize: 10, fontWeight: 600, color: status.color, background: `${status.color}20`, padding: '2px 8px', borderRadius: 20 }}>{status.label}</span>
                  </div>
                  <p style={{ ...S, fontSize: 13, color: '#FFFFFF', marginBottom: 4 }}>{order.items?.[0]?.product_name || 'Produto'}{order.items?.length > 1 ? ` +${order.items.length - 1}` : ''}</p>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <span style={{ ...S, fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>{Number(order.total || 0).toLocaleString()} Kz</span>
                    <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>{order.buyer_email || ''}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {order.status === 'pending' && <>
                      <button onClick={() => updateStatus(order.id, 'confirmed')}
                        style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>✓ Confirmar</button>
                      <button onClick={() => updateStatus(order.id, 'cancelled')}
                        style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: '1px solid rgba(220,38,38,0.3)', background: 'transparent', ...S, fontSize: 12, color: '#dc2626', cursor: 'pointer' }}>✕ Rejeitar</button>
                    </>}
                    {order.status === 'confirmed' && (
                      <button onClick={() => updateStatus(order.id, 'shipped')}
                        style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: 'none', background: '#8b5cf6', ...S, fontSize: 12, fontWeight: 700, color: '#FFFFFF', cursor: 'pointer' }}>🚚 Marcar como enviado</button>
                    )}
                    {(order.status === 'confirmed' || order.status === 'shipped' || order.status === 'processing') && (
                      <button onClick={() => setCheckpointOrderId(order.id)}
                        style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>+ Atualização</button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    
      <HelperBot screen="orders" isSeller={true} />

      {checkpointOrderId && (
        <SellerCheckpointModal
          orderId={checkpointOrderId}
          onClose={() => setCheckpointOrderId(null)}
          onSuccess={() => showToast('Atualização publicada.')}
        />
      )}
      </SellerLayout>
  )
}
