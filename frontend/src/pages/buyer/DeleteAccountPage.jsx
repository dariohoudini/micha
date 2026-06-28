import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { track } from '@/lib/userTrack'

/** DeleteAccountPage — User Process Flow §18.6 3-screen flow. */
const S = { fontFamily: "'DM Sans', sans-serif" }
const REASONS = [
  { v: 'no_longer_needed', l: 'Já não preciso' },
  { v: 'privacy', l: 'Preocupações de privacidade' },
  { v: 'too_many_emails', l: 'Demasiados emails' },
  { v: 'other', l: 'Outro motivo' },
]

export default function DeleteAccountPage() {
  const navigate = useNavigate()
  const logout = useAuthStore(s => s.logout)
  const [step, setStep] = useState(1)
  const [reason, setReason] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }

  const next = () => {
    track('account.delete_step', { from: step, to: step + 1, reason })
    setStep(step + 1)
  }
  const submit = async () => {
    if (confirm.trim().toUpperCase() !== 'DELETE') return
    setBusy(true)
    try {
      await client.post('/api/v1/auth/delete-account/', { reason, confirmation: 'DELETE' })
      track('account.delete_scheduled', { reason })
      show('Conta agendada para eliminação.')
      setTimeout(async () => {
        await logout()
        navigate('/login')
      }, 1500)
    } catch (e) {
      show(e.response?.data?.detail || 'Erro.', 'error')
    } finally { setBusy(false) }
  }

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => step === 1 ? navigate(-1) : setStep(step - 1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Eliminar conta · {step}/3</h1>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
        {step === 1 && (
          <>
            <p style={{ fontSize: 40, marginBottom: 12 }}>⚠️</p>
            <p style={{ ...S, fontSize: 14, color: '#FFF', fontWeight: 600, marginBottom: 12 }}>O que acontece quando elimina a conta</p>
            <ul style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.7, paddingLeft: 20 }}>
              <li>Todas as sessões serão terminadas imediatamente.</li>
              <li>O seu perfil, lista de desejos e cupões serão eliminados.</li>
              <li>Pedidos e transacções podem ser retidos por motivos legais.</li>
              <li>Tem 30 dias para reactivar. Após isso, a eliminação é permanente.</li>
            </ul>
            <button onClick={next}
              style={{ width: '100%', marginTop: 28, padding: '14px 0', borderRadius: 12, border: 'none', background: '#dc2626', ...S, fontSize: 14, fontWeight: 700, color: '#FFF', cursor: 'pointer' }}>Continuar</button>
          </>
        )}
        {step === 2 && (
          <>
            <p style={{ ...S, fontSize: 14, color: '#FFF', fontWeight: 600, marginBottom: 16 }}>Qual o motivo?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {REASONS.map(r => (
                <button key={r.v} onClick={() => setReason(r.v)}
                  style={{ padding: '14px 16px', borderRadius: 12, border: `1.5px solid ${reason === r.v ? '#dc2626' : '#2A2A2A'}`, background: reason === r.v ? 'rgba(220,38,38,0.1)' : 'transparent', ...S, fontSize: 13, color: reason === r.v ? '#dc2626' : '#FFF', cursor: 'pointer', textAlign: 'left' }}>
                  {r.l}
                </button>
              ))}
            </div>
            <button onClick={next} disabled={!reason}
              style={{ width: '100%', marginTop: 28, padding: '14px 0', borderRadius: 12, border: 'none', background: reason ? '#dc2626' : '#2A2A2A', ...S, fontSize: 14, fontWeight: 700, color: reason ? '#FFF' : '#555', cursor: 'pointer' }}>Continuar</button>
          </>
        )}
        {step === 3 && (
          <>
            <p style={{ ...S, fontSize: 14, color: '#FFF', fontWeight: 600, marginBottom: 8 }}>Confirmação final</p>
            <p style={{ ...S, fontSize: 13, color: '#BFBFBF', marginBottom: 14 }}>Escreva <strong style={{ color: '#dc2626' }}>DELETE</strong> para confirmar.</p>
            <input value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="DELETE"
              style={{ width: '100%', background: '#141414', border: `1.5px solid ${confirm.toUpperCase() === 'DELETE' ? '#dc2626' : '#2A2A2A'}`, borderRadius: 12, padding: '14px', ...S, fontSize: 16, color: '#FFF', outline: 'none', boxSizing: 'border-box', textAlign: 'center', letterSpacing: '0.2em', fontFamily: 'monospace' }} />
            <button onClick={submit} disabled={busy || confirm.trim().toUpperCase() !== 'DELETE'}
              style={{ width: '100%', marginTop: 28, padding: '14px 0', borderRadius: 12, border: 'none', background: confirm.trim().toUpperCase() === 'DELETE' ? '#dc2626' : '#2A2A2A', ...S, fontSize: 14, fontWeight: 700, color: confirm.trim().toUpperCase() === 'DELETE' ? '#FFF' : '#555', cursor: 'pointer' }}>
              {busy ? '…' : 'Eliminar a minha conta'}
            </button>
          </>
        )}
      </div>
    </BuyerLayout>
  )
}
