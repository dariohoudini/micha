import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { track } from '@/lib/userTrack'

/** TwoFactorPage — User Process Flow §18.2. TOTP enrol/disable. */
const S = { fontFamily: "'DM Sans', sans-serif" }
const input = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 14, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }

export default function TwoFactorPage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [enabled, setEnabled] = useState(Boolean(user?.two_fa_enabled))
  const [setupData, setSetupData] = useState(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }
  useEffect(() => { track('two_factor.open', { enabled }) }, [enabled])

  const startSetup = async () => {
    setBusy(true)
    try {
      const res = await client.post('/api/v1/auth/2fa/setup/')
      setSetupData(res.data)
      track('two_factor.setup_started', {})
    } catch (e) { show(e.response?.data?.detail || 'Erro.', 'error') } finally { setBusy(false) }
  }

  const confirmEnable = async () => {
    if (!/^\d{6}$/.test(code)) { show('Insira 6 dígitos.', 'error'); return }
    setBusy(true)
    try {
      await client.post('/api/v1/auth/2fa/enable/', { code })
      setEnabled(true); setSetupData(null); setCode('')
      track('two_factor.enabled', {})
      show('2FA activado!')
    } catch (e) { show(e.response?.data?.detail || 'Código inválido.', 'error') } finally { setBusy(false) }
  }

  const disable = async () => {
    const c = prompt('Insira o código TOTP actual para desactivar:')
    if (!c) return
    setBusy(true)
    try {
      await client.post('/api/v1/auth/2fa/disable/', { code: c })
      setEnabled(false)
      track('two_factor.disabled', {})
      show('2FA desactivado.')
    } catch (e) { show(e.response?.data?.detail || 'Erro.', 'error') } finally { setBusy(false) }
  }

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Autenticação de 2 factores</h1>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 100px' }}>
        <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 16, marginBottom: 16 }}>
          <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.6 }}>
            {enabled
              ? '✓ A sua conta está protegida com 2FA. Será solicitado um código a cada login.'
              : 'Acrescente uma camada de segurança. Vai precisar de uma app de autenticação como Google Authenticator ou Authy.'}
          </p>
        </div>
        {!enabled && !setupData && (
          <button onClick={startSetup} disabled={busy}
            style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            {busy ? 'A configurar…' : 'Activar 2FA'}
          </button>
        )}
        {setupData && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14, textAlign: 'center' }}>
              <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 10 }}>Passo 1 — Adicione esta conta na sua app autenticadora</p>
              {setupData.qr_url ? (
                <img src={setupData.qr_url} alt="QR" style={{ width: 200, height: 200, borderRadius: 12, background: '#FFF', padding: 8 }} />
              ) : (
                <p style={{ ...S, fontSize: 11, color: '#C9A84C', wordBreak: 'break-all', fontFamily: 'monospace' }}>{setupData.secret || setupData.otpauth_url}</p>
              )}
              <p style={{ ...S, fontSize: 10, color: '#9A9A9A', marginTop: 8, fontFamily: 'monospace' }}>Segredo: {setupData.secret}</p>
            </div>
            <div>
              <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 6 }}>Passo 2 — Insira o código de 6 dígitos</p>
              <input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000" inputMode="numeric" style={{ ...input, textAlign: 'center', fontSize: 22, letterSpacing: '0.4em', fontFamily: 'monospace' }} />
            </div>
            <button onClick={confirmEnable} disabled={busy || code.length !== 6}
              style={{ padding: '14px 0', borderRadius: 12, border: 'none', background: code.length === 6 ? '#C9A84C' : '#2A2A2A', ...S, fontSize: 14, fontWeight: 700, color: code.length === 6 ? '#0A0A0A' : '#555', cursor: 'pointer' }}>
              {busy ? 'A confirmar…' : 'Confirmar e activar'}
            </button>
          </div>
        )}
        {enabled && (
          <button onClick={disable} disabled={busy}
            style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: '1px solid rgba(220,38,38,0.4)', background: 'transparent', ...S, fontSize: 13, fontWeight: 600, color: '#dc2626', cursor: 'pointer' }}>
            {busy ? '…' : 'Desactivar 2FA'}
          </button>
        )}
      </div>
    </BuyerLayout>
  )
}
