import { useEffect, useState, useCallback } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#1E1E1E'
const RED = '#dc2626'
const GREEN = '#059669'
const AMBER = '#f59e0b'
const S = { fontFamily: "'DM Sans', sans-serif" }

const STATUS_CONFIG = {
  pending:   { label: 'Em análise',  color: AMBER },
  approved:  { label: 'Aprovada',    color: GREEN },
  rejected:  { label: 'Rejeitada',   color: RED },
  completed: { label: 'Concluída',   color: GREEN },
}

const REASON_LABELS = {
  damaged: 'Produto danificado',
  wrong_item: 'Item errado',
  not_as_described: 'Não como descrito',
  missing_parts: 'Peças em falta',
  changed_mind: 'Mudei de ideias',
}

function ReturnCard({ ret, onAction, onPhotoClick }) {
  const [showNote, setShowNote] = useState(false)
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const config = STATUS_CONFIG[ret.status] || STATUS_CONFIG.pending

  const submit = async (newStatus) => {
    setPending(true); setError('')
    try {
      await onAction(ret.id, newStatus, note.trim())
      setShowNote(false); setNote('')
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro.')
    } finally { setPending(false) }
  }

  const inputStyle = {
    width: '100%', background: '#0A0A0A', border: `1px solid ${BORDER}`, borderRadius: 8,
    padding: '8px 10px', ...S, fontSize: 12, color: TEXT, outline: 'none',
    boxSizing: 'border-box', resize: 'vertical',
  }

  return (
    <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ ...S, fontSize: 11, fontWeight: 700, color: GOLD, letterSpacing: '0.04em' }}>#{ret.order_number}</span>
        <span style={{ ...S, fontSize: 10, fontWeight: 600, color: config.color, background: `${config.color}20`, padding: '3px 9px', borderRadius: 20 }}>
          {config.label}
        </span>
      </div>

      <p style={{ ...S, fontSize: 13, color: TEXT, fontWeight: 500, margin: '0 0 4px' }}>
        {ret.buyer_name || ret.buyer_email}
      </p>
      <p style={{ ...S, fontSize: 12, color: MUTED, margin: '0 0 8px' }}>
        Motivo: <span style={{ color: TEXT }}>{REASON_LABELS[ret.reason] || ret.reason}</span> · Recolha: <span style={{ color: TEXT }}>{ret.pickup_method === 'pickup' ? 'em casa' : 'em ponto'}</span>
      </p>

      {ret.description && (
        <p style={{ ...S, fontSize: 12, color: '#CCC', margin: '0 0 8px', padding: '8px 10px', background: '#0A0A0A', borderRadius: 8, borderLeft: `2px solid ${BORDER}`, lineHeight: 1.5 }}>
          {ret.description}
        </p>
      )}

      {ret.photo_url && (
        <button onClick={() => onPhotoClick?.(ret.photo_url)}
          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', marginBottom: 8 }}>
          <img src={ret.photo_url} alt="" style={{ width: 80, height: 80, borderRadius: 8, objectFit: 'cover', border: `1px solid ${BORDER}` }} />
        </button>
      )}

      {ret.admin_note && (
        <p style={{ ...S, fontSize: 11, color: MUTED, padding: '8px 10px', borderLeft: `2px solid ${GOLD}`, background: '#0A0A0A', margin: '0 0 8px' }}>
          <strong style={{ color: GOLD }}>Nota:</strong> {ret.admin_note}
        </p>
      )}

      {/* Action area */}
      {(ret.status === 'pending' || ret.status === 'approved') && (
        showNote ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder="Mensagem ao comprador (opcional)…"
              style={inputStyle}
            />
            {error && <p style={{ ...S, fontSize: 11, color: RED, margin: 0 }}>{error}</p>}
            <div style={{ display: 'flex', gap: 6 }}>
              {ret.status === 'pending' && (
                <>
                  <button onClick={() => submit('approved')} disabled={pending}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: 'none', background: GREEN, ...S, fontSize: 12, fontWeight: 700, color: '#FFF', cursor: 'pointer' }}>
                    {pending ? '...' : '✓ Aprovar'}
                  </button>
                  <button onClick={() => submit('rejected')} disabled={pending}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `1px solid ${RED}`, background: 'transparent', ...S, fontSize: 12, color: RED, cursor: 'pointer' }}>
                    Rejeitar
                  </button>
                </>
              )}
              {ret.status === 'approved' && (
                <button onClick={() => submit('completed')} disabled={pending}
                  style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: 'none', background: GREEN, ...S, fontSize: 12, fontWeight: 700, color: '#FFF', cursor: 'pointer' }}>
                  {pending ? '...' : '✓ Marcar concluída'}
                </button>
              )}
              <button onClick={() => { setShowNote(false); setNote(''); setError('') }} disabled={pending}
                style={{ padding: '8px 14px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'transparent', ...S, fontSize: 12, color: MUTED, cursor: 'pointer' }}>
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <button onClick={() => setShowNote(true)}
            style={{ marginTop: 4, padding: '8px 14px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'transparent', ...S, fontSize: 12, color: GOLD, cursor: 'pointer', width: '100%' }}>
            {ret.status === 'pending' ? 'Aprovar / Rejeitar…' : 'Marcar como concluída…'}
          </button>
        )
      )}
    </div>
  )
}

export default function SellerReturnsList() {
  const [returns, setReturns] = useState([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [lightboxUrl, setLightboxUrl] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = statusFilter !== 'all' ? { status: statusFilter } : {}
      const res = await client.get('/api/v1/orders/returns/seller/', { params })
      setReturns(res.data.results || [])
    } catch { setReturns([]) }
    finally { setLoading(false) }
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const handleAction = async (id, status, admin_note) => {
    const res = await client.patch(`/api/v1/orders/returns/${id}/`, { status, admin_note })
    setReturns(prev => prev.map(r => r.id === id ? res.data : r))
  }

  const STATUS_FILTERS = [
    { v: 'pending', l: 'Em análise' },
    { v: 'approved', l: 'Aprovadas' },
    { v: 'completed', l: 'Concluídas' },
    { v: 'rejected', l: 'Rejeitadas' },
    { v: 'all', l: 'Todas' },
  ]

  return (
    <div>
      {/* Status sub-filter */}
      <div style={{ display: 'flex', gap: 6, padding: '0 0 12px', overflowX: 'auto', scrollbarWidth: 'none' }}>
        {STATUS_FILTERS.map(f => (
          <button key={f.v} onClick={() => setStatusFilter(f.v)}
            style={{ padding: '5px 12px', borderRadius: 20, flexShrink: 0,
              border: `1px solid ${statusFilter === f.v ? GOLD : BORDER}`,
              background: statusFilter === f.v ? 'rgba(201,168,76,0.1)' : 'transparent',
              ...S, fontSize: 11, color: statusFilter === f.v ? GOLD : MUTED, cursor: 'pointer', whiteSpace: 'nowrap' }}>
            {f.l}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <div style={{ width: 24, height: 24, borderRadius: '50%', border: `2px solid ${GOLD}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
        </div>
      ) : returns.length === 0 ? (
        <p style={{ ...S, fontSize: 13, color: MUTED, textAlign: 'center', padding: '40px 0' }}>
          Sem pedidos de devolução {statusFilter !== 'all' ? `(${STATUS_FILTERS.find(f => f.v === statusFilter)?.l.toLowerCase()})` : ''}.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {returns.map(r => (
            <ReturnCard key={r.id} ret={r} onAction={handleAction} onPhotoClick={setLightboxUrl} />
          ))}
        </div>
      )}

      {lightboxUrl && (
        <div onClick={() => setLightboxUrl(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.9)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src={lightboxUrl} alt="" style={{ maxWidth: '92%', maxHeight: '90%', objectFit: 'contain' }} />
          <button onClick={(e) => { e.stopPropagation(); setLightboxUrl(null) }}
            style={{ position: 'absolute', top: 'max(20px, env(safe-area-inset-top))', right: 16, width: 36, height: 36, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', border: 'none', color: '#FFF', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>
      )}
    </div>
  )
}
