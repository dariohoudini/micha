// SellerAnalyticsPage.jsx
import { useState, useEffect } from 'react'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

const formatPrice = (n) => Number(n || 0).toLocaleString() + ' Kz'

export function SellerAnalyticsPage() {
  const [data, setData] = useState(null)
  const [period, setPeriod] = useState(7)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    client.get(`/api/v1/analytics/seller/performance/?period=${period}&include_chart=true`)
      .then(res => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [period])

  const S = { fontFamily: "'DM Sans', sans-serif" }
  const maxRevenue = Math.max(...(data?.chart || []).map(d => d.revenue || 0), 1)

  return (
    <SellerLayout title="Análises">
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            {[7, 14, 30].map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: `1px solid ${period === p ? '#C9A84C' : '#2A2A2A'}`, background: period === p ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: period === p ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                {p} dias
              </button>
            ))}
          </div>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
            </div>
          ) : data ? (<>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {[
                { label: 'Receita', value: formatPrice(data.total_revenue), color: '#C9A84C' },
                { label: 'Pedidos', value: data.total_orders || 0, color: '#FFFFFF' },
                { label: 'Visitas', value: data.total_views || 0, color: '#FFFFFF' },
                { label: 'Avaliação', value: data.avg_rating ? `★ ${Number(data.avg_rating).toFixed(1)}` : '—', color: '#C9A84C' },
              ].map(stat => (
                <div key={stat.label} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
                  <p style={{ ...S, fontSize: 20, fontWeight: 700, color: stat.color, marginBottom: 4 }}>{stat.value}</p>
                  <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{stat.label}</p>
                </div>
              ))}
            </div>
            {data.chart?.length > 0 && (
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16 }}>
                <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#FFFFFF', marginBottom: 16 }}>Receita diária</p>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 80, marginBottom: 8 }}>
                  {data.chart.map((day, i) => (
                    <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                      <div style={{ width: '100%', borderRadius: '3px 3px 0 0', height: `${((day.revenue || 0) / maxRevenue) * 100}%`, minHeight: (day.revenue || 0) > 0 ? 4 : 2, background: i === data.chart.length - 1 ? '#C9A84C' : 'rgba(201,168,76,0.3)' }} />
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  {data.chart.map((day, i) => (
                    <span key={i} style={{ flex: 1, ...S, fontSize: 8, color: '#9A9A9A', textAlign: 'center' }}>{day.day || ''}</span>
                  ))}
                </div>
              </div>
            )}
          </>) : <p style={{ ...S, fontSize: 14, color: '#9A9A9A', textAlign: 'center', padding: '40px 0' }}>Sem dados disponíveis.</p>}
        </div>
      </div>
    </SellerLayout>
  )
}

export default SellerAnalyticsPage
