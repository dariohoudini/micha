import { useState } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#2A2A2A'
const RED = '#dc2626'
const S = { fontFamily: "'DM Sans', sans-serif" }

// Common checkpoint codes — seller picks one, or types a custom description
const CHECKPOINT_CODES = [
  { v: 'processing', l: 'Em preparação', icon: '📦' },
  { v: 'shipped', l: 'Enviado', icon: '🚚' },
  { v: 'in_transit', l: 'Em trânsito', icon: '🛣️' },
  { v: 'arrived', l: 'Chegou ao hub', icon: '📍' },
  { v: 'out_for_delivery', l: 'Saiu para entrega', icon: '🛵' },
  { v: 'update', l: 'Outra atualização', icon: '✍️' },
]

const COMMON_LOCATIONS = ['Luanda', 'Benguela', 'Huambo', 'Lobito', 'Lubango', 'Cabinda']

export default function SellerCheckpointModal({ orderId, onClose, onSuccess }) {
  const [code, setCode] = useState('in_transit')
  const [description, setDescription] = useState('')
  const [location, setLocation] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const inputStyle = {
    width: '100%', background: CARD, border: `1px solid ${BORDER}`,
    borderRadius: 10, padding: '11px 14px', ...S, fontSize: 13,
    color: TEXT, outline: 'none', boxSizing: 'border-box',
  }

  const submit = async () => {
    if (!code) { setError('Escolhe um tipo de evento.'); return }
    if (!description.trim() && code === 'update') {
      setError('Descreve a atualização.'); return
    }
    setSubmitting(true); setError('')
    try {
      const res = await client.post(`/api/v1/orders/${orderId}/tracking/`, {
        code,
        description: description.trim(),
        location: location.trim(),
        is_visible_to_buyer: true,
      })
      onSuccess?.(res.data)
      onClose?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao adicionar evento.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 200,
      display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: '100%', maxWidth: 520, background: '#0F0F0F',
        borderRadius: '20px 20px 0 0', borderTop: `1px solid ${BORDER}`,
        maxHeight: '90vh', overflowY: 'auto',
        paddingBottom: 'max(24px, env(safe-area-inset-bottom))',
      }}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: BORDER }} />
        </div>

        <div style={{ padding: '0 20px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <h2 style={{ fontFamily: "'Playfair Display',serif", fontSize: 19, fontWeight: 700, color: TEXT, margin: 0 }}>
              Adicionar atualização
            </h2>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED, fontSize: 22, lineHeight: 1, padding: 4 }}>×</button>
          </div>
          <p style={{ ...S, fontSize: 12, color: MUTED, margin: '0 0 18px' }}>
            O comprador vê esta atualização no rastreio do pedido.
          </p>

          {/* Code chips */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Tipo de evento</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 18 }}>
            {CHECKPOINT_CODES.map(c => (
              <button key={c.v} onClick={() => { setCode(c.v); setError('') }}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '8px 12px', borderRadius: 20,
                  border: `1px solid ${code === c.v ? GOLD : BORDER}`,
                  background: code === c.v ? 'rgba(201,168,76,0.08)' : CARD,
                  ...S, fontSize: 12, color: code === c.v ? GOLD : TEXT,
                  cursor: 'pointer',
                }}>
                <span>{c.icon}</span>{c.l}
              </button>
            ))}
          </div>

          {/* Description */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Descrição <span style={{ color: '#555' }}>{code !== 'update' ? '(opcional)' : ''}</span>
          </p>
          <textarea
            value={description}
            onChange={e => { setDescription(e.target.value); setError('') }}
            rows={2}
            maxLength={300}
            placeholder="Ex: Saiu do armazém de Luanda, chega amanhã"
            style={{ ...inputStyle, resize: 'none', lineHeight: 1.5, marginBottom: 18 }}
          />

          {/* Location */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Local <span style={{ color: '#555' }}>(opcional)</span>
          </p>
          <input
            value={location}
            onChange={e => setLocation(e.target.value)}
            maxLength={120}
            placeholder="Luanda – Centro de distribuição"
            style={{ ...inputStyle, marginBottom: 8 }}
          />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 18 }}>
            {COMMON_LOCATIONS.map(loc => (
              <button key={loc} onClick={() => setLocation(loc)}
                style={{ padding: '4px 10px', borderRadius: 16, border: `1px solid ${BORDER}`, background: 'transparent', ...S, fontSize: 11, color: MUTED, cursor: 'pointer' }}>
                {loc}
              </button>
            ))}
          </div>

          {error && (
            <p style={{ ...S, fontSize: 12, color: RED, marginBottom: 12 }}>{error}</p>
          )}

          <button onClick={submit} disabled={submitting}
            style={{
              width: '100%', padding: '14px 0', borderRadius: 14, border: 'none',
              background: submitting ? 'rgba(201,168,76,0.4)' : GOLD,
              ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A',
              cursor: submitting ? 'not-allowed' : 'pointer',
            }}>
            {submitting ? 'A enviar…' : 'Publicar atualização'}
          </button>
        </div>
      </div>
    </div>
  )
}
