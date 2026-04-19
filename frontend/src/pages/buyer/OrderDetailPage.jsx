import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import OrderTimeline from '@/components/buyer/OrderTimeline'
import { formatPrice } from '@/components/buyer/mockData'

// Mock order for demo
const MOCK_ORDER = {
  id: 'ORD-DEMO01',
  status: 'shipped',
  date: '12 Abr 2026',
  total: 193500,
  delivery: 0,
  items: [
    { id: '1', name: 'Vestido Capulana Premium', price: 8500, quantity: 1, seller: 'Moda Luanda', image_color: '#8B4513' },
    { id: '2', name: 'Smartphone Samsung A55', price: 185000, quantity: 1, seller: 'TechShop Angola', image_color: '#1a1a2e' },
  ],
  address: { name: 'João Silva', phone: '+244 912 345 678', address: 'Rua da Missão, 45, Luanda', province: 'Luanda' },
  payment: 'Multicaixa Express',
  timestamps: {
    pending: '12 Abr 2026, 09:15',
    confirmed: '12 Abr 2026, 09:45',
    shipped: '12 Abr 2026, 14:30',
  },
}

export default function OrderDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const order = MOCK_ORDER // Replace with useOrder(id) when backend ready

  return (
    <BuyerLayout>
      <div style={{ padding: '52px 16px 0', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button onClick={() => navigate('/orders')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <div>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Detalhe do pedido</h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', marginTop: 2 }}>{order.id}</p>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Tracking timeline */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 20 }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 20 }}>Rastreio do pedido</h3>
            <OrderTimeline status={order.status} timestamps={order.timestamps} />
          </div>

          {/* Items */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid #1E1E1E' }}>
              <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF' }}>Produtos ({order.items.length})</h3>
            </div>
            {order.items.map((item, i) => (
              <div key={item.id} style={{ display: 'flex', gap: 12, padding: 14, borderBottom: i < order.items.length - 1 ? '1px solid #1E1E1E' : 'none' }}>
                <div style={{ width: 56, height: 56, borderRadius: 10, background: item.image_color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginBottom: 4 }}>{item.seller}</p>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>×{item.quantity}</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#C9A84C' }}>{formatPrice(item.price * item.quantity)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Delivery address */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Endereço de entrega</h3>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500, color: '#FFFFFF' }}>{order.address.name}</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: 2 }}>{order.address.phone}</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: 2 }}>{order.address.address}, {order.address.province}</p>
          </div>

          {/* Payment summary */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Resumo de pagamento</h3>
            {[
              { label: 'Subtotal', value: formatPrice(order.total) },
              { label: 'Entrega', value: order.delivery === 0 ? 'Grátis' : formatPrice(order.delivery), green: true },
              { label: 'Método', value: order.payment },
            ].map(row => (
              <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{row.label}</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: row.green ? '#059669' : '#FFFFFF' }}>{row.value}</span>
              </div>
            ))}
            <div style={{ height: 1, background: '#2A2A2A', margin: '10px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>Total pago</span>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(order.total)}</span>
            </div>
          </div>

          {/* Actions */}
          {order.status !== 'delivered' && (
            <button className="btn-secondary">Contactar suporte</button>
          )}
          {order.status === 'delivered' && (
            <button className="btn-primary">Avaliar produtos</button>
          )}
        </div>
      </div>
    </BuyerLayout>
  )
}
