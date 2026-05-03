import { useState, useEffect } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const GREEN = '#059669'

const PREFS = [
  { key: 'order_updates', label: 'Actualizações de pedidos', sub: 'Confirmação, envio, entrega' },
  { key: 'price_drops', label: 'Descidas de preço', sub: 'Quando produtos na wishlist ficam mais baratos' },
  { key: 'back_in_stock', label: 'Disponível novamente', sub: 'Quando produtos esgotados voltam ao stock' },
  { key: 'promotions', label: 'Promoções e Flash Sales', sub: 'Ofertas especiais e descontos' },
  { key: 'cart_reminders', label: 'Lembrete de carrinho', sub: 'Quando tens produtos no carrinho há mais de 2h' },
  { key: 'weekly_digest', label: 'Resumo semanal', sub: 'Selecção personalizada de produtos' },
  { key: 'seller_messages', label: 'Mensagens de vendedores', sub: 'Respostas e actualizações de vendedores' },
]

export default function NotificationPreferences() {
  const [prefs, setPrefs] = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    client.get('/api/v1/ai/notification-preferences/')
      .then(r => setPrefs(r.data || {}))
      .catch(() => {
        const defaults = {}
        PREFS.forEach(p => defaults[p.key] = true)
        setPrefs(defaults)
      })
  }, [])

  const toggle = async (key) => {
    const newPrefs = { ...prefs, [key]: !prefs[key] }
    setPrefs(newPrefs)
    setSaving(true)
    try {
      await client.put('/api/v1/ai/notification-preferences/', newPrefs)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {}
    setSaving(false)
  }

  return (
    <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Preferências de notificações</p>
        {saved && <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GREEN }}>Guardado ✓</span>}
      </div>
      {PREFS.map((pref, i) => (
        <div key={pref.key} style={{ padding: '13px 16px', borderBottom: i < PREFS.length - 1 ? `1px solid ${BORDER}` : 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: TEXT, margin: '0 0 2px' }}>{pref.label}</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>{pref.sub}</p>
          </div>
          <button onClick={() => toggle(pref.key)} style={{
            width: 44, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer',
            background: prefs[pref.key] ? GREEN : BORDER, position: 'relative', padding: 0, flexShrink: 0,
            transition: 'background 0.2s'
          }}>
            <div style={{
              width: 18, height: 18, borderRadius: '50%', background: TEXT,
              position: 'absolute', top: 3, left: prefs[pref.key] ? 23 : 3,
              transition: 'left 0.2s'
            }} />
          </button>
        </div>
      ))}
    </div>
  )
}
