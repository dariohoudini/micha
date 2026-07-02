/**
 * MICHA Express — User Action Buttons
 * Block user, Report seller/product
 */
import { useState } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const RED = '#EF4444'

// ─── Block User Button ────────────────────────────────────────────
export function BlockUserButton({ userId, username }) {
  const [blocked, setBlocked] = useState(false)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)

  const handleBlock = async () => {
    setLoading(true)
    try {
      if (blocked) {
        await client.delete(`/api/v1/accounts/unblock/${userId}/`)
        setBlocked(false)
      } else {
        await client.post('/api/v1/accounts/block/', { blocked: userId })
        setBlocked(true)
      }
      setOpen(false)
    } catch {}
    setLoading(false)
  }

  return (
    <>
      <button onClick={() => setOpen(true)} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: 6,
        color: blocked ? RED : MUTED,
        fontFamily: "'DM Sans', sans-serif", fontSize: 12, padding: '8px 0',
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
        </svg>
        {blocked ? 'Desbloquear utilizador' : 'Bloquear utilizador'}
      </button>

      {open && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div onClick={() => setOpen(false)} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)' }} />
          <div style={{ position: 'relative', background: '#111', borderRadius: '20px 20px 0 0', padding: 24, width: '100%', maxWidth: 480 }}>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: TEXT, margin: '0 0 8px' }}>
              {blocked ? 'Desbloquear' : 'Bloquear'} {username}?
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: '0 0 20px', lineHeight: 1.6 }}>
              {blocked
                ? 'Este utilizador voltará a poder enviar-te mensagens e ver o teu perfil.'
                : 'Este utilizador não poderá enviar-te mensagens nem ver o teu perfil.'}
            </p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setOpen(false)} style={{ flex: 1, padding: '13px', borderRadius: 12, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 14, cursor: 'pointer' }}>
                Cancelar
              </button>
              <button onClick={handleBlock} disabled={loading} style={{ flex: 1, padding: '13px', borderRadius: 12, border: 'none', background: RED, color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                {loading ? '...' : blocked ? 'Desbloquear' : 'Bloquear'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Report Button ────────────────────────────────────────────────
export function ReportButton({ targetType, targetId, targetName }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const reasons = [
    'Produto falso ou imitação',
    'Vendedor desonesto',
    'Conteúdo ofensivo',
    'Fraude ou esquema',
    'Item proibido',
    'Outro motivo',
  ]

  const handleSubmit = async () => {
    if (!reason) return
    setLoading(true)
    try {
      await client.post('/api/v1/reports/create/', {
        target_type: targetType,
        target_id: targetId,
        reason,
      })
      setSubmitted(true)
    } catch {}
    setLoading(false)
  }

  return (
    <>
      <button onClick={() => setOpen(true)} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: 6,
        color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12, padding: '8px 0',
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
        Denunciar
      </button>

      {open && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div onClick={() => setOpen(false)} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)' }} />
          <div style={{ position: 'relative', background: '#111', borderRadius: '20px 20px 0 0', padding: 24, width: '100%', maxWidth: 480, maxHeight: '80vh', overflowY: 'auto' }}>
            {submitted ? (
              <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 600, color: TEXT, margin: '0 0 8px' }}>Denúncia enviada</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: '0 0 20px' }}>A equipa MICHA irá analisar a sua denúncia em 24 horas.</p>
                <button onClick={() => { setOpen(false); setSubmitted(false); setReason('') }} style={{ padding: '12px 24px', borderRadius: 12, border: 'none', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                  Fechar
                </button>
              </div>
            ) : (
              <>
                <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: TEXT, margin: '0 0 6px' }}>Denunciar {targetName}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: '0 0 16px' }}>Selecciona o motivo da denúncia</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                  {reasons.map(r => (
                    <button key={r} onClick={() => setReason(r)} style={{
                      padding: '12px 14px', borderRadius: 10, border: `1.5px solid ${reason === r ? GOLD : BORDER}`,
                      background: reason === r ? 'rgba(201,168,76,0.08)' : CARD,
                      color: reason === r ? GOLD : TEXT, fontFamily: "'DM Sans', sans-serif",
                      fontSize: 13, cursor: 'pointer', textAlign: 'left',
                    }}>{r}</button>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={() => setOpen(false)} style={{ flex: 1, padding: '13px', borderRadius: 12, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 14, cursor: 'pointer' }}>
                    Cancelar
                  </button>
                  <button onClick={handleSubmit} disabled={!reason || loading} style={{ flex: 2, padding: '13px', borderRadius: 12, border: 'none', background: reason ? RED : BORDER, color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, cursor: reason ? 'pointer' : 'not-allowed', opacity: !reason ? 0.5 : 1 }}>
                    {loading ? 'A enviar...' : 'Enviar denúncia'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// ─── Buyer Protection Button ──────────────────────────────────────
export function BuyerProtectionButton({ orderId }) {
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleClaim = async () => {
    setLoading(true)
    try {
      await client.post('/api/v1/moderation/buyer-protection/', { order_id: orderId })
      setSubmitted(true)
    } catch {}
    setLoading(false)
  }

  if (submitted) return (
    <div style={{ padding: '12px 14px', borderRadius: 12, background: 'rgba(5,150,105,0.08)', border: '1px solid rgba(5,150,105,0.3)' }}>
      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#059669', margin: 0 }}>
        ✅ Protecção MICHA solicitada. Entraremos em contacto em 24h.
      </p>
    </div>
  )

  return (
    <button onClick={handleClaim} disabled={loading} style={{
      width: '100%', padding: '13px', borderRadius: 12, border: '1.5px solid rgba(201,168,76,0.4)',
      background: 'rgba(201,168,76,0.08)', color: GOLD,
      fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, cursor: 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
      {loading ? 'A processar...' : 'Solicitar protecção MICHA'}
    </button>
  )
}

export default { BlockUserButton, ReportButton, BuyerProtectionButton }
