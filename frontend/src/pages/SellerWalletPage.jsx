import { useNavigate } from 'react-router-dom'

export default function SellerWalletPage() {
  const navigate = useNavigate()

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => navigate('/seller')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
            Carteira
          </h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Balance card */}
          <div style={{
            borderRadius: 20, padding: 24,
            background: 'linear-gradient(135deg, #C9A84C 0%, #A67C35 100%)',
          }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(0,0,0,0.6)', fontWeight: 500, marginBottom: 6 }}>
              SALDO DISPONÍVEL
            </p>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 36, fontWeight: 700, color: '#0A0A0A', marginBottom: 20 }}>
              0 Kz
            </p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button style={{
                flex: 1, padding: '10px 0', borderRadius: 12,
                background: 'rgba(0,0,0,0.15)', border: 'none', cursor: 'pointer',
                fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#0A0A0A',
              }}>
                Levantar
              </button>
              <button style={{
                flex: 1, padding: '10px 0', borderRadius: 12,
                background: 'rgba(0,0,0,0.1)', border: '1px solid rgba(0,0,0,0.2)', cursor: 'pointer',
                fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#0A0A0A',
              }}>
                Histórico
              </button>
            </div>
          </div>

          {/* Stats row */}
          {[
            { label: 'Total ganho', value: '0 Kz' },
            { label: 'A processar', value: '0 Kz' },
            { label: 'Levantado', value: '0 Kz' },
          ].map(stat => (
            <div key={stat.label} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E',
              padding: '14px 16px',
            }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{stat.label}</span>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF' }}>{stat.value}</span>
            </div>
          ))}

          {/* Empty transactions */}
          <div style={{ marginTop: 8 }}>
            <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
              Transações recentes
            </h2>
            <div style={{
              background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E',
              padding: 32, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
            }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', textAlign: 'center' }}>
                Sem transações ainda. As vendas aparecerão aqui.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
