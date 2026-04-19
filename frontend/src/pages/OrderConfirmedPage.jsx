import { useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'

export default function OrderConfirmedPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const orderId = location.state?.orderId || 'ORD-XXXXXX'
  const [scale, setScale] = useState(0.5)

  useEffect(() => {
    setTimeout(() => setScale(1), 100)
  }, [])

  return (
    <div style={{
      height: '100%', background: '#0A0A0A',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '0 32px', textAlign: 'center',
    }}>
      {/* Success icon */}
      <div style={{
        width: 100, height: 100, borderRadius: '50%',
        background: 'rgba(5,150,105,0.1)',
        border: '2px solid rgba(5,150,105,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 28,
        transform: `scale(${scale})`,
        transition: 'transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
      }}>
        <svg width="44" height="44" viewBox="0 0 24 24" fill="none"
          stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>

      <h1 style={{
        fontFamily: "'Playfair Display', serif",
        fontSize: 30, fontWeight: 700, color: '#FFFFFF',
        marginBottom: 10, lineHeight: 1.2,
      }}>
        Pedido confirmado!
      </h1>

      <p style={{
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 14, color: '#9A9A9A', lineHeight: 1.6, marginBottom: 8,
      }}>
        O seu pedido foi recebido com sucesso.
      </p>

      {/* Order ID */}
      <div style={{
        background: '#1E1E1E', border: '1px solid #2A2A2A',
        borderRadius: 12, padding: '10px 20px', marginBottom: 32,
      }}>
        <span style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 12, color: '#9A9A9A', letterSpacing: '0.05em',
        }}>
          Nº do pedido{' '}
        </span>
        <span style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 13, fontWeight: 700, color: '#C9A84C',
        }}>
          {orderId}
        </span>
      </div>

      {/* Delivery info */}
      <div style={{
        background: 'rgba(201,168,76,0.06)',
        border: '1px solid rgba(201,168,76,0.15)',
        borderRadius: 14, padding: 16, marginBottom: 32, width: '100%',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#C9A84C">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#C9A84C' }}>
            Entrega em andamento
          </span>
        </div>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.5 }}>
          Irá receber uma notificação quando o seu pedido estiver a caminho.
        </p>
      </div>

      <button className="btn-primary" onClick={() => navigate('/home')} style={{ marginBottom: 12 }}>
        Continuar a comprar
      </button>

      <button
        onClick={() => navigate('/orders')}
        style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 13, color: '#9A9A9A',
          background: 'none', border: 'none', cursor: 'pointer',
        }}>
        Ver os meus pedidos
      </button>
    </div>
  )
}
