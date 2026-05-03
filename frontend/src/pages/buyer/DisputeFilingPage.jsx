/**
 * src/pages/buyer/DisputeFilingPage.jsx
 * Buyer files a dispute against a delivered order.
 */
import { useState } from 'react'
import { useNavigate, useLocation, useParams } from 'react-router-dom'
import client from '@/api/client'

const REASONS = [
  { value: 'not_received', label: 'Produto não recebido' },
  { value: 'not_as_described', label: 'Produto diferente do anunciado' },
  { value: 'damaged', label: 'Produto danificado na entrega' },
  { value: 'seller_silent', label: 'Vendedor não responde' },
  { value: 'wrong_item', label: 'Item errado enviado' },
  { value: 'missing_parts', label: 'Peças/acessórios em falta' },
]

export default function DisputeFilingPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const params = useParams()
  const orderId = params.orderId || location.state?.order_id

  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [photos, setPhotos] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async () => {
    if (!reason || description.trim().length < 20) return
    setLoading(true)
    setError(null)
    try {
      const data = new FormData()
      data.append('order_id', orderId)
      data.append('reason', reason)
      data.append('description', description)
      photos.forEach(p => data.append('photos', p))

      await client.post('/api/v1/disputes/file/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setSubmitted(true)
    } catch (err) {
      setError(err.response?.data?.error || 'Erro ao submeter disputa.')
    } finally {
      setLoading(false)
    }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  if (submitted) return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A', padding: '32px 24px', textAlign: 'center' }}>
      <div style={{ width: 70, height: 70, borderRadius: '50%', background: 'rgba(245,158,11,0.1)', border: '2px solid rgba(245,158,11,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
        <span style={{ fontSize: 32 }}>⚠️</span>
      </div>
      <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>Disputa aberta</h1>
      <p style={{ ...S, fontSize: 14, color: '#9A9A9A', lineHeight: 1.7, marginBottom: 32 }}>
        A sua disputa foi registada. O vendedor tem 48 horas para responder.
        Receberá uma notificação com as actualizações.
      </p>
      <button onClick={() => navigate('/orders')} className="btn-primary" style={{ width: '100%' }}>
        Ver os meus pedidos
      </button>
    </div>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>
      {/* Header */}
      <div style={{ padding: '0 20px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Abrir disputa</h1>
        </div>
        <p style={{ ...S, fontSize: 13, color: '#9A9A9A', marginLeft: 34 }}>
          Tem 7 dias após a entrega para abrir uma disputa.
        </p>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '8px 20px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Reason */}
          <div>
            <label style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8, display: 'block' }}>
              Motivo da disputa
            </label>
            {REASONS.map(r => (
              <button key={r.value} onClick={() => setReason(r.value)} type="button"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', padding: '13px 16px', borderRadius: 12, border: `1.5px solid ${reason === r.value ? '#C9A84C' : '#1E1E1E'}`, background: reason === r.value ? 'rgba(201,168,76,0.08)' : '#141414', cursor: 'pointer', marginBottom: 6, textAlign: 'left' }}>
                <span style={{ ...S, fontSize: 14, color: reason === r.value ? '#C9A84C' : '#FFFFFF' }}>{r.label}</span>
                {reason === r.value && (
                  <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  </div>
                )}
              </button>
            ))}
          </div>

          {/* Description */}
          <div>
            <label style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }}>
              Descrição do problema
            </label>
            <textarea value={description} onChange={e => setDescription(e.target.value)}
              placeholder="Descreva o problema em detalhe (mínimo 20 caracteres)..."
              rows={4}
              style={{ width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '13px 16px', ...S, fontSize: 14, color: '#FFFFFF', outline: 'none', resize: 'vertical', boxSizing: 'border-box' }} />
            <p style={{ ...S, fontSize: 11, color: description.length < 20 ? '#f59e0b' : '#059669', marginTop: 4 }}>
              {description.length < 20 ? `${20 - description.length} caracteres mínimos restantes` : '✓ Descrição válida'}
            </p>
          </div>

          {/* Evidence photos */}
          <div>
            <label style={{ ...S, fontSize: 12, fontWeight: 600, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }}>
              Fotos de evidência (opcional, máx. 5)
            </label>
            <input type="file" accept="image/*" multiple id="dispute-photos" style={{ display: 'none' }}
              onChange={e => setPhotos(prev => [...prev, ...Array.from(e.target.files)].slice(0, 5))} />
            <label htmlFor="dispute-photos"
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', borderRadius: 12, border: '2px dashed #2A2A2A', background: '#141414', cursor: 'pointer' }}>
              <span style={{ fontSize: 20 }}>📷</span>
              <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Adicionar fotos ({photos.length}/5)</span>
            </label>

            {photos.length > 0 && (
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                {photos.map((p, i) => (
                  <div key={i} style={{ position: 'relative', width: 60, height: 60 }}>
                    <img src={URL.createObjectURL(p)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 8 }} />
                    <button onClick={() => setPhotos(prev => prev.filter((_, idx) => idx !== i))}
                      style={{ position: 'absolute', top: -4, right: -4, width: 16, height: 16, borderRadius: '50%', background: '#dc2626', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 9 }}>✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Warning */}
          <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: 14 }}>
            <p style={{ ...S, fontSize: 12, color: '#f59e0b', lineHeight: 1.6 }}>
              ⚠️ Ao abrir uma disputa, o pagamento ao vendedor ficará temporariamente suspenso até à resolução. Use apenas em caso de problema real.
            </p>
          </div>

          {error && (
            <div style={{ background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 10, padding: 12 }}>
              <p style={{ ...S, fontSize: 13, color: '#ef4444' }}>{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: '14px 20px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
        <button onClick={handleSubmit} className="btn-primary"
          disabled={!reason || description.trim().length < 20 || loading}
          style={{ opacity: !reason || description.trim().length < 20 ? 0.4 : 1 }}>
          {loading ? 'A submeter...' : '⚠️ Abrir disputa'}
        </button>
      </div>
    </div>
  )
}
