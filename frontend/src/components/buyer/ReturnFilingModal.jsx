import { useState } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#2A2A2A'
const RED = '#dc2626'
const S = { fontFamily: "'DM Sans', sans-serif" }

const REASONS = [
  { v: 'damaged', l: 'Produto danificado', icon: '💔' },
  { v: 'wrong_item', l: 'Item errado', icon: '🔄' },
  { v: 'not_as_described', l: 'Não como descrito', icon: '📋' },
  { v: 'missing_parts', l: 'Peças em falta', icon: '🧩' },
  { v: 'changed_mind', l: 'Mudei de ideias', icon: '🤔' },
]

const PICKUPS = [
  { v: 'pickup', l: 'Recolha em casa', sub: 'Vamos buscar' },
  { v: 'dropoff', l: 'Entrega em ponto', sub: 'Vais a um ponto' },
]

export default function ReturnFilingModal({ orderId, onClose, onSuccess }) {
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [pickup, setPickup] = useState('pickup')
  const [photo, setPhoto] = useState(null)
  const [photoPreview, setPhotoPreview] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handlePhoto = (e) => {
    const f = e.target.files?.[0]
    if (!f || !f.type.startsWith('image/')) return
    setPhoto(f)
    setPhotoPreview(URL.createObjectURL(f))
  }

  const submit = async () => {
    if (!reason) { setError('Selecciona um motivo.'); return }
    setSubmitting(true); setError('')
    try {
      const fd = new FormData()
      fd.append('reason', reason)
      fd.append('pickup_method', pickup)
      if (description.trim()) fd.append('description', description.trim())
      if (photo) fd.append('photo', photo)
      const res = await client.post(`/api/v1/orders/${orderId}/return/`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      onClose?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao submeter. Tente novamente.')
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle = {
    width: '100%', background: CARD, border: `1px solid ${BORDER}`,
    borderRadius: 10, padding: '11px 14px', ...S, fontSize: 13,
    color: TEXT, outline: 'none', boxSizing: 'border-box',
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
              Pedir devolução
            </h2>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED, fontSize: 22, lineHeight: 1, padding: 4 }}>×</button>
          </div>
          <p style={{ ...S, fontSize: 12, color: MUTED, margin: '0 0 18px' }}>
            Conta-nos o que aconteceu — vamos analisar em até 24h.
          </p>

          {/* Reason */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Motivo</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 18 }}>
            {REASONS.map(r => (
              <button key={r.v} onClick={() => { setReason(r.v); setError('') }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
                  borderRadius: 12, border: `1px solid ${reason === r.v ? GOLD : BORDER}`,
                  background: reason === r.v ? 'rgba(201,168,76,0.08)' : CARD,
                  cursor: 'pointer', textAlign: 'left',
                }}>
                <span style={{ fontSize: 18 }}>{r.icon}</span>
                <span style={{ ...S, fontSize: 13, fontWeight: 500, color: TEXT, flex: 1 }}>{r.l}</span>
                {reason === r.v && (
                  <span style={{ width: 18, height: 18, borderRadius: '50%', background: GOLD, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round"><polyline points="20 6 9 17 4 12" /></svg>
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Description */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Descreve o problema <span style={{ color: '#555' }}>(opcional)</span>
          </p>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="Ex: O produto chegou com um arranhão no canto..."
            style={{ ...inputStyle, resize: 'none', lineHeight: 1.5, marginBottom: 18 }}
          />

          {/* Photo */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Foto <span style={{ color: '#555' }}>(opcional, ajuda a aprovar)</span>
          </p>
          <div style={{ marginBottom: 18 }}>
            {photoPreview ? (
              <div style={{ position: 'relative', display: 'inline-block' }}>
                <img src={photoPreview} alt="" style={{ width: 100, height: 100, borderRadius: 10, objectFit: 'cover', border: `1px solid ${BORDER}` }} />
                <button onClick={() => { URL.revokeObjectURL(photoPreview); setPhoto(null); setPhotoPreview(null) }}
                  style={{ position: 'absolute', top: -6, right: -6, width: 22, height: 22, borderRadius: '50%', background: RED, border: 'none', color: '#FFF', cursor: 'pointer', fontSize: 13, lineHeight: 1 }}>×</button>
              </div>
            ) : (
              <label style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 100, height: 100, borderRadius: 10, border: `1px dashed ${BORDER}`,
                cursor: 'pointer', color: MUTED, fontSize: 28,
              }}>
                +<input type="file" accept="image/*" onChange={handlePhoto} style={{ display: 'none' }} />
              </label>
            )}
          </div>

          {/* Pickup method */}
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Como devolver</p>
          <div style={{ display: 'flex', gap: 8, marginBottom: 22 }}>
            {PICKUPS.map(p => (
              <button key={p.v} onClick={() => setPickup(p.v)}
                style={{
                  flex: 1, padding: '12px 10px', borderRadius: 12,
                  border: `1px solid ${pickup === p.v ? GOLD : BORDER}`,
                  background: pickup === p.v ? 'rgba(201,168,76,0.08)' : CARD,
                  cursor: 'pointer', textAlign: 'left',
                }}>
                <p style={{ ...S, fontSize: 13, fontWeight: 600, color: pickup === p.v ? GOLD : TEXT, margin: 0 }}>{p.l}</p>
                <p style={{ ...S, fontSize: 11, color: MUTED, margin: '2px 0 0' }}>{p.sub}</p>
              </button>
            ))}
          </div>

          {error && (
            <p style={{ ...S, fontSize: 12, color: RED, marginBottom: 12 }}>{error}</p>
          )}

          <button onClick={submit} disabled={submitting || !reason}
            style={{
              width: '100%', padding: '14px 0', borderRadius: 14, border: 'none',
              background: submitting || !reason ? 'rgba(201,168,76,0.4)' : GOLD,
              ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A',
              cursor: submitting || !reason ? 'not-allowed' : 'pointer',
            }}>
            {submitting ? 'A submeter…' : 'Submeter pedido'}
          </button>
        </div>
      </div>
    </div>
  )
}
