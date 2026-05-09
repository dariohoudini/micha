import api from '@/api/client'
/**
 * MICHA Express — 22 UX Components
 */
import { useState, useEffect } from 'react'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const GREEN = '#059669'
const RED = '#EF4444'
const BLUE = '#3B82F6'
const fmt = (n) => n?.toLocaleString('pt-AO') + ' Kz'

export function VerifiedSellerBadge({ tier = 'verified' }) {
  const tiers = {
    identity: { label: 'Identidade verificada', color: BLUE },
    business: { label: 'Negócio verificado', color: GOLD },
    top: { label: 'Top Seller', color: '#F59E0B' },
    verified: { label: 'Vendedor verificado', color: GREEN },
  }
  const t = tiers[tier] || tiers.verified
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 6, background: `${t.color}18`, border: `1px solid ${t.color}40` }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={t.color} strokeWidth="2" strokeLinecap="round">
        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: t.color }}>{t.label}</span>
    </div>
  )
}

export function ResponseTimeBadge({ minutes = 15 }) {
  const color = minutes <= 15 ? GREEN : minutes <= 60 ? GOLD : MUTED
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 6, background: `${color}12`, border: `1px solid ${color}30` }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color, fontWeight: 500 }}>Responde em ~{minutes} min</span>
    </div>
  )
}

export function SellerOfflineToggle({ isOpen: initial = true, onToggle }) {
  const [isOpen, setIsOpen] = useState(initial)
  const toggle = async () => {
    setLoading(true)
    try {
      const res = await api.post('/api/v1/stores/toggle-open/')
      setIsOpen(res.data.is_open)
      onToggle?.(res.data.is_open)
    } catch { setIsOpen(p => !p) }
    finally { setLoading(false) }
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', background: CARD, borderRadius: 14, border: `1.5px solid ${isOpen ? 'rgba(5,150,105,0.3)' : BORDER}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: isOpen ? GREEN : RED }} />
        <div>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Loja {isOpen ? 'aberta' : 'fechada'}</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '2px 0 0' }}>{isOpen ? 'A receber pedidos' : 'Pedidos pausados'}</p>
        </div>
      </div>
      <button onClick={toggle} style={{ width: 48, height: 26, borderRadius: 13, border: 'none', cursor: 'pointer', background: isOpen ? GREEN : BORDER, position: 'relative', padding: 0 }}>
        <div style={{ width: 20, height: 20, borderRadius: '50%', background: TEXT, position: 'absolute', top: 3, left: isOpen ? 25 : 3, transition: 'left 0.3s' }} />
      </button>
    </div>
  )
}

export function FlashSaleCountdown({ endsAt, discount, salePrice, originalPrice }) {
  const [timeLeft, setTimeLeft] = useState({ h: 0, m: 0, s: 0 })
  useEffect(() => {
    const tick = () => {
      const diff = Math.max(0, new Date(endsAt) - new Date())
      setTimeLeft({ h: Math.floor(diff / 3600000), m: Math.floor((diff % 3600000) / 60000), s: Math.floor((diff % 60000) / 1000) })
    }
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id)
  }, [endsAt])
  const pad = n => String(n).padStart(2, '0')
  return (
    <div style={{ background: 'rgba(239,68,68,0.08)', border: '1.5px solid rgba(239,68,68,0.3)', borderRadius: 14, padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: RED }}>FLASH SALE -{discount}%</span>
        <div style={{ display: 'flex', gap: 4 }}>
          {[pad(timeLeft.h), pad(timeLeft.m), pad(timeLeft.s)].map((v, i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: RED, background: 'rgba(239,68,68,0.15)', padding: '2px 6px', borderRadius: 6 }}>{v}</span>
              {i < 2 && <span style={{ color: RED }}>:</span>}
            </span>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: RED }}>{fmt(salePrice)}</span>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, textDecoration: 'line-through' }}>{fmt(originalPrice)}</span>
      </div>
    </div>
  )
}

function relTime(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}m atrás`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h atrás`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d atrás`
  return new Date(iso).toLocaleDateString('pt-AO', { day: '2-digit', month: 'short' })
}

export function ProductQASection({ productId, isSeller = false }) {
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [newQ, setNewQ] = useState('')
  const [posting, setPosting] = useState(false)
  const [answerInputs, setAnswerInputs] = useState({})
  const [answering, setAnswering] = useState({})
  const [error, setError] = useState('')

  useEffect(() => {
    if (!productId) return
    setLoading(true)
    api.get(`/api/v1/products/${productId}/qa/`)
      .then(r => setQuestions(r.data.results || r.data || []))
      .catch(() => setQuestions([]))
      .finally(() => setLoading(false))
  }, [productId])

  const askQuestion = async () => {
    const text = newQ.trim()
    if (!text || posting) return
    setPosting(true); setError('')
    try {
      const res = await api.post(`/api/v1/products/${productId}/qa/`, { question: text })
      setQuestions(prev => [res.data, ...prev])
      setNewQ('')
    } catch (err) {
      if (err.response?.status === 401) setError('Faça login para perguntar.')
      else setError(err.response?.data?.detail || 'Erro ao enviar.')
    } finally { setPosting(false) }
  }

  const submitAnswer = async (qaId) => {
    const text = (answerInputs[qaId] || '').trim()
    if (!text || answering[qaId]) return
    setAnswering(p => ({ ...p, [qaId]: true }))
    try {
      const res = await api.patch(`/api/v1/products/qa/${qaId}/answer/`, { answer: text })
      setQuestions(prev => prev.map(q => q.id === qaId ? res.data : q))
      setAnswerInputs(p => ({ ...p, [qaId]: '' }))
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao responder.')
    } finally {
      setAnswering(p => ({ ...p, [qaId]: false }))
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[1, 2].map(i => (
          <div key={i} className="skeleton" style={{ height: 60, borderRadius: 12 }} />
        ))}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {questions.length === 0 ? (
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, fontStyle: 'italic', margin: 0 }}>
          Sem perguntas ainda. {isSeller ? 'Aguarde perguntas dos compradores.' : 'Seja o primeiro a perguntar.'}
        </p>
      ) : (
        questions.map(q => (
          <div key={q.id} style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, margin: 0 }}>
                <strong style={{ color: BLUE }}>P:</strong> {q.question}
              </p>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, flexShrink: 0 }}>{relTime(q.created_at)}</span>
            </div>
            {q.asker_name && q.asker_name !== 'Anonymous' && (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '0 0 6px' }}>— {q.asker_name}</p>
            )}
            {q.answer ? (
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, margin: '6px 0 2px' }}>
                  <strong style={{ color: GOLD }}>R:</strong> {q.answer}
                </p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: 0 }}>
                  {q.answered_by_name || 'Vendedor'} · {relTime(q.answered_at)}
                </p>
              </div>
            ) : isSeller ? (
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <input
                  value={answerInputs[q.id] || ''}
                  onChange={e => setAnswerInputs(p => ({ ...p, [q.id]: e.target.value }))}
                  onKeyDown={e => { if (e.key === 'Enter') submitAnswer(q.id) }}
                  placeholder="Responder…"
                  disabled={answering[q.id]}
                  style={{ flex: 1, padding: '8px 12px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 8, color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 12, outline: 'none' }}
                />
                <button
                  onClick={() => submitAnswer(q.id)}
                  disabled={answering[q.id] || !(answerInputs[q.id] || '').trim()}
                  style={{ padding: '8px 14px', borderRadius: 8, border: 'none', background: GOLD, color: '#000', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, opacity: answering[q.id] ? 0.5 : 1 }}>
                  {answering[q.id] ? '...' : 'Responder'}
                </button>
              </div>
            ) : (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '6px 0 0', fontStyle: 'italic' }}>
                Aguardando resposta do vendedor…
              </p>
            )}
          </div>
        ))
      )}

      {!isSeller && (
        <div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={newQ}
              onChange={e => { setNewQ(e.target.value); setError('') }}
              onKeyDown={e => { if (e.key === 'Enter') askQuestion() }}
              placeholder="Fazer uma pergunta…"
              disabled={posting}
              style={{ flex: 1, padding: '11px 14px', background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 13, outline: 'none' }}
            />
            <button
              onClick={askQuestion}
              disabled={posting || !newQ.trim()}
              style={{ padding: '11px 18px', borderRadius: 12, border: 'none', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: posting || !newQ.trim() ? 0.5 : 1 }}>
              {posting ? '...' : 'Perguntar'}
            </button>
          </div>
          {error && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: RED, margin: '6px 0 0' }}>{error}</p>}
        </div>
      )}
    </div>
  )
}

export function PriceDropAlertToggle() {
  const [active, setActive] = useState(false)
  return (
    <button onClick={() => setActive(!active)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 12, border: `1.5px solid ${active ? 'rgba(5,150,105,0.4)' : BORDER}`, background: active ? 'rgba(5,150,105,0.08)' : 'none', cursor: 'pointer', width: '100%' }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill={active ? GREEN : 'none'} stroke={active ? GREEN : MUTED} strokeWidth="2" strokeLinecap="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: active ? GREEN : TEXT, fontWeight: 500 }}>{active ? 'Alerta activado' : 'Alertar quando o preço baixar'}</span>
    </button>
  )
}

export function DeliverySlotPicker({ selected, onSelect }) {
  const slots = [{ id: 'morning', label: 'Manhã', time: '8h–12h', icon: '🌅' }, { id: 'afternoon', label: 'Tarde', time: '12h–17h', icon: '☀️' }, { id: 'evening', label: 'Noite', time: '17h–21h', icon: '🌙' }]
  return (
    <div>
      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: '0 0 10px' }}>Janela de entrega preferida</p>
      <div style={{ display: 'flex', gap: 10 }}>
        {slots.map(s => (
          <button key={s.id} onClick={() => onSelect(s.id)} style={{ flex: 1, padding: '12px 8px', borderRadius: 12, border: `1.5px solid ${selected === s.id ? GOLD : BORDER}`, background: selected === s.id ? 'rgba(201,168,76,0.08)' : CARD, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 20 }}>{s.icon}</span>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: selected === s.id ? GOLD : TEXT }}>{s.label}</span>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED }}>{s.time}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function PayoutScheduleCalendar() {
  const [payouts, setPayouts] = useState([])
  const [total, setTotal] = useState(0)
  useEffect(() => {
    api.get('/api/v1/payments/payouts/schedule/').then(res => {
      const data = res.data.upcoming_payouts || []
      setPayouts(data.map(p => ({
        date: new Date(p.release_at).toLocaleDateString('pt-AO', { weekday: 'short', day: 'numeric', month: 'short' }),
        amount: parseFloat(p.amount),
        order: String(p.order_id).slice(0, 8).toUpperCase(),
      })))
      setTotal(parseFloat(res.data.total_pending || 0))
    }).catch(() => {})
  }, [])
  return (
    <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between' }}>
        <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Calendário de pagamentos</h3>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD }}>Próximos 30 dias</span>
      </div>
      <div style={{ padding: 16 }}>
        <div style={{ background: BG, borderRadius: 10, padding: '10px 14px', marginBottom: 12 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 2px' }}>Total a receber</p>
          <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: GOLD, margin: 0 }}>{fmt(payouts.reduce((s, p) => s + p.amount, 0))}</p>
        </div>
        {payouts.map((p, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: i < 2 ? `1px solid ${BORDER}` : 'none' }}>
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, margin: '0 0 2px' }}>{p.date}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>{p.order}</p>
            </div>
            <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 14, fontWeight: 700, color: GOLD }}>{fmt(p.amount)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function WhatsAppShareButton({ product }) {
  const share = () => {
    const text = encodeURIComponent(`Encontrei isto na MICHA Express!\n${product?.title} por ${fmt(product?.price)}\n${window.location.href}`)
    window.open(`https://wa.me/?text=${text}`, '_blank')
  }
  return (
    <button onClick={share} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '11px 16px', borderRadius: 12, border: '1.5px solid rgba(37,211,102,0.3)', background: 'rgba(37,211,102,0.08)', cursor: 'pointer', width: '100%', justifyContent: 'center' }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="#25D366"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#25D366' }}>Partilhar no WhatsApp</span>
    </button>
  )
}

export function DeliveryETA({ minutes = 18 }) {
  const [eta, setEta] = useState(minutes)
  useEffect(() => { const id = setInterval(() => setEta(p => Math.max(0, p - 1)), 60000); return () => clearInterval(id) }, [])
  return (
    <div style={{ background: 'rgba(5,150,105,0.08)', border: '1.5px solid rgba(5,150,105,0.3)', borderRadius: 14, padding: 14, display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ width: 44, height: 44, borderRadius: 12, background: GREEN, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"><rect x="1" y="3" width="15" height="13" /><polygon points="16 8 20 8 23 11 23 16 16 16 16 8" /><circle cx="5.5" cy="18.5" r="2.5" /><circle cx="18.5" cy="18.5" r="2.5" /></svg>
      </div>
      <div>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: GREEN, fontWeight: 600, margin: '0 0 2px' }}>Entregador a caminho</p>
        <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: TEXT, margin: 0 }}>{eta > 0 ? `~${eta} min` : 'A chegar!'}</p>
      </div>
    </div>
  )
}

export function LoyaltyPointsDisplay({ points = 450, tier = 'silver' }) {
  const tiers = { bronze: { label: 'Bronze', color: '#CD7F32', next: 500, nextTier: 'Prata' }, silver: { label: 'Prata', color: '#C0C0C0', next: 1000, nextTier: 'Ouro' }, gold: { label: 'Ouro', color: GOLD, next: null } }
  const t = tiers[tier]
  return (
    <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 2px', textTransform: 'uppercase' }}>Micha Stars</p>
          <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, color: GOLD, margin: 0 }}>{points.toLocaleString()}</p>
        </div>
        <div style={{ padding: '4px 10px', borderRadius: 8, background: `${t.color}20`, border: `1px solid ${t.color}40`, alignSelf: 'flex-start' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: t.color }}>{t.label}</span>
        </div>
      </div>
      {t.next && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED }}>Progresso para {t.nextTier}</span>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED }}>{points}/{t.next}</span>
          </div>
          <div style={{ height: 6, background: BORDER, borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${(points/t.next)*100}%`, height: '100%', background: GOLD, borderRadius: 3 }} />
          </div>
        </div>
      )}
      <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
        <button style={{ flex: 1, padding: '10px', borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12, cursor: 'pointer' }}>Ver histórico</button>
        <button style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Resgatar pontos</button>
      </div>
    </div>
  )
}

export function GuestCheckoutOption({ onGuest, onLogin }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <button onClick={onLogin} style={{ padding: '14px', borderRadius: 14, border: 'none', cursor: 'pointer', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600 }}>Entrar na minha conta</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ flex: 1, height: 1, background: BORDER }} />
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED }}>ou</span>
        <div style={{ flex: 1, height: 1, background: BORDER }} />
      </div>
      <button onClick={onGuest} style={{ padding: '14px', borderRadius: 14, border: `1.5px solid ${BORDER}`, cursor: 'pointer', background: 'none', color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 14 }}>Continuar como visitante</button>
    </div>
  )
}

export default function MichaUXComponents() {
  const [slot, setSlot] = useState(null)
  return (
    <div style={{ background: BG, minHeight: '100vh', padding: '40px 16px' }}>
      <div style={{ maxWidth: 480, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, color: TEXT }}>UX Components Demo</h1>
        <DeliveryETA minutes={18} />
        <FlashSaleCountdown endsAt={new Date(Date.now() + 18000000).toISOString()} discount={25} salePrice={135000} originalPrice={180000} />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <VerifiedSellerBadge tier="verified" />
          <VerifiedSellerBadge tier="business" />
          <VerifiedSellerBadge tier="top" />
        </div>
        <ResponseTimeBadge minutes={10} />
        <SellerOfflineToggle isOpen={true} />
        <ProductQASection isSeller={false} />
        <PriceDropAlertToggle />
        <DeliverySlotPicker selected={slot} onSelect={setSlot} />
        <PayoutScheduleCalendar />
        <LoyaltyPointsDisplay points={450} tier="silver" />
        <WhatsAppShareButton product={{ title: 'Samsung Galaxy S24', price: 180000 }} />
        <GuestCheckoutOption onGuest={() => {}} onLogin={() => {}} />
      </div>
    </div>
  )
}

export function SplitPaymentUI({ total = 185000, walletBalance = 50000 }) {
  const [walletAmount, setWalletAmount] = useState(Math.min(walletBalance, total))
  const multicaixaAmount = Math.max(0, total - walletAmount)
  const fmt = (n) => n?.toLocaleString('pt-AO') + ' Kz'
  const GOLD = '#C9A84C', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', GREEN = '#059669', BG = '#0A0A0A'
  return (
    <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 16 }}>
      <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: '0 0 14px' }}>Pagamento dividido</h3>
      <div style={{ background: BG, borderRadius: 10, padding: '10px 14px', marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED }}>Saldo da carteira</span>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: GREEN, fontWeight: 600 }}>{fmt(walletBalance)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED }}>Total do pedido</span>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: TEXT, fontWeight: 600 }}>{fmt(total)}</span>
        </div>
      </div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED }}>Usar da carteira</span>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: GREEN, fontWeight: 600 }}>{fmt(walletAmount)}</span>
        </div>
        <input type="range" min="0" max={Math.min(walletBalance, total)} value={walletAmount} onChange={e => setWalletAmount(+e.target.value)} style={{ width: '100%', accentColor: GREEN }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(5,150,105,0.08)', borderRadius: 10 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: GREEN }}>Carteira MICHA</span>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: GREEN }}>{fmt(walletAmount)}</span>
        </div>
        {multicaixaAmount > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(201,168,76,0.08)', borderRadius: 10 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: GOLD }}>Multicaixa Express</span>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: GOLD }}>{fmt(multicaixaAmount)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function FlashSaleCreator({ onSave }) {
  const [discount, setDiscount] = useState(20)
  const [hours, setHours] = useState(24)
  const originalPrice = 180000
  const salePrice = originalPrice * (1 - discount / 100)
  const fmt = (n) => n?.toLocaleString('pt-AO') + ' Kz'
  const RED = '#EF4444', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A'
  return (
    <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}` }}>
        <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Criar Flash Sale</h3>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED }}>Desconto</span>
            <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: RED }}>-{discount}%</span>
          </div>
          <input type="range" min="5" max="70" value={discount} onChange={e => setDiscount(+e.target.value)} style={{ width: '100%', accentColor: RED }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {[6, 12, 24, 48].map(h => (
            <button key={h} onClick={() => setHours(h)} style={{ flex: 1, padding: '8px 4px', borderRadius: 10, border: `1.5px solid ${hours === h ? RED : BORDER}`, background: hours === h ? 'rgba(239,68,68,0.1)' : 'none', color: hours === h ? RED : MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12, cursor: 'pointer' }}>{h}h</button>
          ))}
        </div>
        <div style={{ background: BG, borderRadius: 12, padding: 14, display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, textDecoration: 'line-through' }}>{fmt(originalPrice)}</span>
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: RED }}>{fmt(salePrice)}</span>
        </div>
        <button onClick={async () => {
          try {
            const res = await api.post('/api/v1/promotions/seller/flash-sales/', {
              discount_percent: discount,
              duration_hours: hours,
              sale_price: salePrice,
            })
            onSave?.(res.data)
          } catch (e) {
            onSave?.({ discount, hours, salePrice })
          }
        }} style={{ padding: '13px', borderRadius: 12, border: 'none', cursor: 'pointer', background: RED, color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600 }}>
          Activar Flash Sale por {hours}h
        </button>
      </div>
    </div>
  )
}

export function ProductBoostUI({ onBoost }) {
  const [duration, setDuration] = useState(24)
  const prices = { 24: 2500, 48: 4500, 168: 12000 }
  const fmt = (n) => n?.toLocaleString('pt-AO') + ' Kz'
  const GOLD = '#C9A84C', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A'
  return (
    <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}` }}>
        <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Promover produto</h3>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {Object.entries(prices).map(([h, p]) => (
            <button key={h} onClick={() => setDuration(+h)} style={{ flex: 1, padding: '10px 6px', borderRadius: 10, border: `1.5px solid ${duration === +h ? GOLD : BORDER}`, background: duration === +h ? 'rgba(201,168,76,0.1)' : 'none', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: duration === +h ? GOLD : TEXT }}>{+h >= 168 ? '7 dias' : `${h}h`}</span>
              <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 13, fontWeight: 700, color: duration === +h ? GOLD : MUTED }}>{fmt(p)}</span>
            </button>
          ))}
        </div>
        <button onClick={async () => {
          try {
            await api.post('/api/v1/promotions/seller/coupons/', {
              type: 'boost',
              duration_hours: duration,
              amount: prices[duration],
            })
            onBoost?.({ duration, price: prices[duration] })
          } catch { onBoost?.({ duration, price: prices[duration] }) }
        }} style={{ padding: '13px', borderRadius: 12, border: 'none', cursor: 'pointer', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600 }}>
          Pagar {fmt(prices[duration])} e promover
        </button>
      </div>
    </div>
  )
}

export function SocialOrderShareCard({ order }) {
  const share = () => {
    const text = encodeURIComponent(`Acabei de comprar na MICHA Express!\n${order?.items || 'Samsung Galaxy S24'}\nEntrega expressa em Luanda 🚀`)
    window.open(`https://wa.me/?text=${text}`, '_blank')
  }
  const CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A'
  return (
    <div style={{ background: `linear-gradient(135deg, ${CARD} 0%, ${BG} 100%)`, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 20, textAlign: 'center' }}>
      <div style={{ width: 48, height: 48, borderRadius: 14, background: 'rgba(201,168,76,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', fontSize: 24 }}>🛍️</div>
      <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: TEXT, margin: '0 0 4px' }}>Partilha a tua compra!</p>
      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '0 0 16px' }}>Mostra aos teus amigos o que compraste</p>
      <button onClick={share} style={{ padding: '11px 20px', borderRadius: 12, border: 'none', cursor: 'pointer', background: '#25D366', color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8, margin: '0 auto' }}>
        Partilhar no WhatsApp
      </button>
    </div>
  )
}
