/**
 * MICHA Express — Seller Dashboard UX
 * Covers: 29 (Today's sales), 30 (Revenue chart), 31 (Best products),
 * 33 (Conversion rate), 40 (AI description generator)
 */
import { useState } from 'react'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

const fmt = (n) => n.toLocaleString('pt-AO') + ' Kz'

const WEEKLY_DATA = [
  { day: 'Seg', revenue: 85000, orders: 3 },
  { day: 'Ter', revenue: 120000, orders: 5 },
  { day: 'Qua', revenue: 65000, orders: 2 },
  { day: 'Qui', revenue: 180000, orders: 7 },
  { day: 'Sex', revenue: 240000, orders: 9 },
  { day: 'Sáb', revenue: 310000, orders: 12 },
  { day: 'Dom', revenue: 95000, orders: 4 },
]

const BEST_PRODUCTS = [
  { id: 1, title: 'Samsung Galaxy S24', revenue: 540000, orders: 3, views: 847, color: '#1a1a40' },
  { id: 2, title: 'AirPods Pro 2nd Gen', revenue: 255000, orders: 3, views: 512, color: '#1a2a1a' },
  { id: 3, title: 'Capinha Leather S24', revenue: 60000, orders: 5, views: 234, color: '#2a1a1a' },
]

// ─── Today's Sales Card ──────────────────────────────────────────────────────
export function TodaySalesCard() {
  const stats = [
    { label: 'Receita hoje', value: fmt(310000), change: '+23%', up: true, icon: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
    { label: 'Pedidos', value: '12', change: '+4', up: true, icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2' },
    { label: 'Visitantes', value: '1.2k', change: '+18%', up: true, icon: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z' },
    { label: 'Conversão', value: '3.2%', change: '-0.4%', up: false, icon: 'M22 12h-4l-3 9L9 3l-3 9H2' },
  ]

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {stats.map((s, i) => (
          <div key={i} style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 14, padding: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={GOLD} strokeWidth="1.5" strokeLinecap="round">
                <path d={s.icon} />
              </svg>
              <span style={{
                fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600,
                color: s.up ? '#059669' : '#EF4444',
                background: s.up ? 'rgba(5,150,105,0.1)' : 'rgba(239,68,68,0.1)',
                padding: '2px 6px', borderRadius: 4
              }}>{s.change}</span>
            </div>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: TEXT, margin: '0 0 2px' }}>{s.value}</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>{s.label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Revenue Chart ───────────────────────────────────────────────────────────
export function RevenueChart() {
  const [period, setPeriod] = useState('week')
  const maxRevenue = Math.max(...WEEKLY_DATA.map(d => d.revenue))

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 16, padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Receita</h3>
          <div style={{ display: 'flex', gap: 6 }}>
            {['week', 'month'].map(p => (
              <button key={p} onClick={() => setPeriod(p)} style={{
                padding: '4px 10px', borderRadius: 8, border: `1px solid ${period === p ? GOLD : BORDER}`,
                background: period === p ? 'rgba(201,168,76,0.1)' : 'none',
                color: period === p ? GOLD : MUTED,
                fontFamily: "'DM Sans', sans-serif", fontSize: 11, cursor: 'pointer'
              }}>{p === 'week' ? 'Semana' : 'Mês'}</button>
            ))}
          </div>
        </div>

        {/* Bar chart */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 100 }}>
          {WEEKLY_DATA.map((d, i) => {
            const height = (d.revenue / maxRevenue) * 100
            const isToday = i === 5
            return (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                <div style={{ width: '100%', position: 'relative' }}>
                  <div style={{
                    width: '100%', height: height,
                    background: isToday ? GOLD : 'rgba(201,168,76,0.25)',
                    borderRadius: '4px 4px 0 0',
                    transition: 'height 0.5s ease',
                    minHeight: 4
                  }} />
                </div>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: isToday ? GOLD : MUTED }}>{d.day}</span>
              </div>
            )
          })}
        </div>

        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between' }}>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 2px' }}>Total esta semana</p>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: GOLD, margin: 0 }}>
              {fmt(WEEKLY_DATA.reduce((s, d) => s + d.revenue, 0))}
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 2px' }}>Vs semana anterior</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#059669', margin: 0 }}>+18.4%</p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Best Products Widget ────────────────────────────────────────────────────
export function BestProductsWidget() {
  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 16, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Melhores produtos</h3>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD }}>Este mês</span>
        </div>
        {BEST_PRODUCTS.map((p, i) => (
          <div key={p.id} style={{ padding: '12px 16px', borderBottom: i < 2 ? `1px solid ${BORDER}` : 'none', display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: BORDER, width: 20, flexShrink: 0 }}>{i + 1}</span>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: p.color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: TEXT, margin: '0 0 2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</p>
              <div style={{ display: 'flex', gap: 10 }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED }}>{p.orders} pedidos</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED }}>{p.views} visitas</span>
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 13, fontWeight: 700, color: GOLD, margin: 0 }}>{fmt(p.revenue)}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '2px 0 0' }}>receita</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── AI Description Generator ────────────────────────────────────────────────
export function AIDescriptionGenerator() {
  const [state, setState] = useState('idle') // idle | loading | done
  const [result, setResult] = useState(null)
  const [copied, setCopied] = useState(false)

  const generate = async () => {
    setState('loading')
    await new Promise(r => setTimeout(r, 1500))
    setResult({
      title: 'Samsung Galaxy S24 128GB — Preto Phantom',
      description: 'Experimente o futuro na palma da sua mão com o Samsung Galaxy S24. Equipado com processador Snapdragon 8 Gen 3, câmera de 50MP com IA integrada e ecrã Dynamic AMOLED de 6,2" a 120Hz. Bateria de 4.000mAh com carregamento rápido de 25W. Garantia oficial de 12 meses. Entrega expressa disponível em Luanda.',
    })
    setState('done')
  }

  const copy = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 16, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(201,168,76,0.15)', border: `1px solid rgba(201,168,76,0.3)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={GOLD} strokeWidth="2" strokeLinecap="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <div>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Gerador de descrição IA</h3>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>Carregue uma foto, a IA escreve por si</p>
          </div>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Photo upload area */}
          <div style={{
            border: `2px dashed ${BORDER}`, borderRadius: 12, padding: '24px 16px',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, cursor: 'pointer'
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="1.5" strokeLinecap="round">
              <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: 0 }}>Toque para carregar foto do produto</p>
          </div>

          <button onClick={generate} disabled={state === 'loading'} style={{
            width: '100%', padding: '13px', borderRadius: 12, border: 'none', cursor: 'pointer',
            background: state === 'loading' ? BORDER : GOLD,
            color: state === 'loading' ? MUTED : '#000',
            fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            transition: 'all 0.2s'
          }}>
            {state === 'loading' ? (
              <>
                <div style={{ width: 14, height: 14, border: `2px solid ${MUTED}`, borderTopColor: TEXT, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
                A gerar descrição...
              </>
            ) : 'Gerar com IA'}
          </button>

          {result && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, animation: 'fadeIn 0.3s ease' }}>
              <style>{`@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}`}</style>

              <div style={{ background: BG, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Título sugerido</span>
                  <button onClick={() => copy(result.title)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  </button>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, margin: 0, lineHeight: 1.4 }}>{result.title}</p>
              </div>

              <div style={{ background: BG, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Descrição sugerida</span>
                  <button onClick={() => copy(result.description)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  </button>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, margin: 0, lineHeight: 1.6 }}>{result.description}</p>
              </div>

              {copied && (
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669', textAlign: 'center', margin: 0 }}>
                  Copiado para a área de transferência
                </p>
              )}

              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={generate} style={{ flex: 1, padding: '10px', borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12, cursor: 'pointer' }}>
                  Gerar outra versão
                </button>
                <button style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                  Usar esta versão
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Full Dashboard Demo ─────────────────────────────────────────────────────
export default function SellerDashboardUX() {
  const [tab, setTab] = useState('overview')

  return (
    <div style={{ background: BG, minHeight: '100vh', paddingBottom: 40 }}>
      <div style={{ maxWidth: 480, margin: '0 auto' }}>

        {/* Header */}
        <div style={{ padding: '40px 16px 16px' }}>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, color: TEXT, margin: '0 0 4px' }}>Painel de Vendedor</h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: 0 }}>Seller dashboard UX demo</p>
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', padding: '0 16px 16px', gap: 8 }}>
          {[['overview', 'Visão geral'], ['ai', 'IA']].map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} style={{
              padding: '7px 14px', borderRadius: 10, border: `1px solid ${tab === key ? GOLD : BORDER}`,
              background: tab === key ? 'rgba(201,168,76,0.1)' : 'none',
              color: tab === key ? GOLD : MUTED,
              fontFamily: "'DM Sans', sans-serif", fontSize: 13, cursor: 'pointer'
            }}>{label}</button>
          ))}
        </div>

        {tab === 'overview' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <TodaySalesCard />
            <RevenueChart />
            <BestProductsWidget />
          </div>
        ) : (
          <AIDescriptionGenerator />
        )}
      </div>
    </div>
  )
}
