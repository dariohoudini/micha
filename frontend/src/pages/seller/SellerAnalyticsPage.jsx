import { useState, useMemo } from 'react'
import SellerLayout from '@/layouts/SellerLayout'
import { formatPrice } from '@/components/buyer/mockData'

const PERIOD_DATA = {
  'Hoje': {
    revenue: 17000, orders: 1, visitors: 234, conversion: 0.4,
    avgOrder: 17000, returnRate: 0, rating: 4.7,
    chart: [0, 0, 3000, 8000, 0, 6000, 0],
    days: ['09h', '11h', '13h', '15h', '17h', '19h', '21h'],
    topProducts: [
      { name: 'Vestido Capulana Premium', sales: 1, revenue: 17000, pct: 100 },
    ],
  },
  '7 dias': {
    revenue: 53500, orders: 5, visitors: 892, conversion: 0.56,
    avgOrder: 10700, returnRate: 1.2, rating: 4.7,
    chart: [12000, 0, 18000, 4500, 28000, 0, 8500],
    days: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
    topProducts: [
      { name: 'Vestido Capulana Premium', sales: 3, revenue: 25500, pct: 100 },
      { name: 'Colar de Missangas', sales: 1, revenue: 4500, pct: 55 },
      { name: 'Bolsa de Couro', sales: 1, revenue: 28000, pct: 72 },
    ],
  },
  '30 dias': {
    revenue: 214000, orders: 22, visitors: 3841, conversion: 0.57,
    avgOrder: 9727, returnRate: 0.9, rating: 4.8,
    chart: [28000, 45000, 32000, 18000, 67000, 41000, 55000],
    days: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'],
    topProducts: [
      { name: 'Bolsa de Couro', sales: 8, revenue: 224000, pct: 100 },
      { name: 'Vestido Capulana', sales: 12, revenue: 102000, pct: 78 },
      { name: 'Colar de Missangas', sales: 15, revenue: 67500, pct: 62 },
    ],
  },
  '3 meses': {
    revenue: 687000, orders: 74, visitors: 12450, conversion: 0.59,
    avgOrder: 9284, returnRate: 1.1, rating: 4.7,
    chart: [187000, 214000, 286000, 0, 0, 0, 0],
    days: ['Fev', 'Mar', 'Abr', '', '', '', ''],
    topProducts: [
      { name: 'Bolsa de Couro', sales: 28, revenue: 784000, pct: 100 },
      { name: 'Vestido Capulana', sales: 34, revenue: 289000, pct: 76 },
      { name: 'Colar de Missangas', sales: 42, revenue: 189000, pct: 58 },
    ],
  },
}

const PERIODS = ['Hoje', '7 dias', '30 dias', '3 meses']

export default function SellerAnalyticsPage() {
  const [period, setPeriod] = useState('7 dias')
  const data = PERIOD_DATA[period]
  const maxVal = Math.max(...data.chart.filter(v => v > 0))

  return (
    <SellerLayout title="Análises">
      {/* Period selector */}
      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, paddingBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              style={{ padding: '7px 16px', borderRadius: 50, flexShrink: 0, border: `1.5px solid ${period === p ? '#C9A84C' : '#2A2A2A'}`, background: period === p ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: period === p ? 600 : 400, color: period === p ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', transition: 'all 0.2s' }}>
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Revenue card with chart */}
          <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 4 }}>Receita — {period}</p>
                <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, color: '#C9A84C' }}>
                  {formatPrice(data.revenue)}
                </p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669', marginTop: 2 }}>
                  {data.orders} pedido{data.orders !== 1 ? 's' : ''}
                </p>
              </div>
              <div style={{ background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 20, padding: '4px 12px' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#059669' }}>↑ Activo</span>
              </div>
            </div>

            {/* Bar chart */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 100, marginBottom: 8 }}>
              {data.chart.map((val, i) => (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end', position: 'relative' }}>
                  {val > 0 && val === Math.max(...data.chart) && (
                    <div style={{ position: 'absolute', top: -22, left: '50%', transform: 'translateX(-50%)', background: '#C9A84C', borderRadius: 6, padding: '2px 6px', whiteSpace: 'nowrap' }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>{formatPrice(val)}</span>
                    </div>
                  )}
                  <div style={{
                    width: '100%',
                    height: val > 0 ? `${(val / maxVal) * 100}%` : '4px',
                    minHeight: 4,
                    borderRadius: '4px 4px 0 0',
                    background: val > 0 && val === Math.max(...data.chart) ? '#C9A84C' : val > 0 ? 'rgba(201,168,76,0.3)' : '#1E1E1E',
                    transition: 'height 0.4s ease',
                  }} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {data.days.map((d, i) => (
                <span key={i} style={{ flex: 1, fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: '#9A9A9A', textAlign: 'center' }}>{d}</span>
              ))}
            </div>
          </div>

          {/* KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[
              { label: 'Visitantes', value: data.visitors.toLocaleString(), sub: 'à sua loja', color: '#3b82f6' },
              { label: 'Conversão', value: `${data.conversion}%`, sub: 'visitas → compras', color: '#059669' },
              { label: 'Pedido médio', value: formatPrice(data.avgOrder), sub: 'por encomenda', color: '#C9A84C' },
              { label: 'Taxa devolução', value: `${data.returnRate}%`, sub: period, color: data.returnRate < 2 ? '#059669' : '#f59e0b' },
              { label: 'Avaliação', value: `${data.rating} ★`, sub: 'média dos clientes', color: '#f59e0b' },
              { label: 'Pedidos', value: data.orders.toString(), sub: period, color: '#8b5cf6' },
            ].map(kpi => (
              <div key={kpi.label} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 20, fontWeight: 700, color: kpi.color, marginBottom: 2 }}>{kpi.value}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF', marginBottom: 2 }}>{kpi.label}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>{kpi.sub}</p>
              </div>
            ))}
          </div>

          {/* Top products */}
          <div>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>
              Produtos mais vendidos — {period}
            </h3>
            {data.topProducts.length === 0 ? (
              <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 24, textAlign: 'center' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Sem dados suficientes para este período.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {data.topProducts.map((p, i) => (
                  <div key={p.name} style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C', flexShrink: 0 }}>#{i + 1}</span>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                      </div>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C', flexShrink: 0, marginLeft: 8 }}>{formatPrice(p.revenue)}</span>
                    </div>
                    <div style={{ height: 4, background: '#2A2A2A', borderRadius: 2, marginBottom: 6 }}>
                      <div style={{ height: '100%', borderRadius: 2, background: '#C9A84C', width: `${p.pct}%`, transition: 'width 0.5s ease' }} />
                    </div>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>{p.sales} vendido{p.sales !== 1 ? 's' : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Tips */}
          <div style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 14, padding: 16 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#C9A84C', marginBottom: 8 }}>💡 Dica para aumentar vendas</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.6 }}>
              {data.conversion < 0.5
                ? 'A sua taxa de conversão está abaixo da média. Melhore as fotos e descrições dos produtos.'
                : 'Boa taxa de conversão! Adicione mais produtos para aumentar a receita total.'
              }
            </p>
          </div>

        </div>
      </div>
    </SellerLayout>
  )
}
