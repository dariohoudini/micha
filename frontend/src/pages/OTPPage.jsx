import { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore as useAuth } from '@/stores/authStore'
import { authAPI } from '@/api/auth'

export default function OTPPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuth(s => s.login)

  const email = location.state?.email || ''
  const context = location.state?.context || 'register'

  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [countdown, setCountdown] = useState(60)
  const [canResend, setCanResend] = useState(false)
  const inputs = useRef([])

  useEffect(() => {
    if (countdown <= 0) { setCanResend(true); return }
    const t = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [countdown])

  const handleDigit = (index, value) => {
    if (!/^\d?$/.test(value)) return
    const next = [...digits]
    next[index] = value
    setDigits(next)
    setError('')
    if (value && index < 5) inputs.current[index + 1]?.focus()
    if (!value && index > 0) inputs.current[index - 1]?.focus()
  }

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputs.current[index - 1]?.focus()
    }
  }

  const handlePaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 6) {
      setDigits(pasted.split(''))
      inputs.current[5]?.focus()
    }
  }

  const handleVerify = async () => {
    const otp = digits.join('')
    if (otp.length < 6) { setError('Insira o código completo de 6 dígitos.'); return }
    setLoading(true)
    try {
      if (context === 'register') {
        // POST { email, otp } → Django VerifyEmailView
        await authAPI.verifyEmail(email, otp)
        // After email verified, go to login
        navigate('/login', { state: { verified: true } })
      } else if (context === 'reset') {
        // Go to reset password page with the otp
        navigate('/reset-password', { state: { email, otp } })
      }
    } catch {
      setError('Código inválido ou expirado. Tente novamente.')
      setDigits(['', '', '', '', '', ''])
      inputs.current[0]?.focus()
    } finally {
      setLoading(false)
    }
  }

  const handleResend = async () => {
    if (!canResend) return
    setCanResend(false)
    setCountdown(60)
    setError('')
    try {
      await authAPI.resendOTP(email)
    } catch {
      setError('Erro ao reenviar código.')
    }
  }

  const filled = digits.join('').length === 6

  return (
    <div style={{ minHeight: '100%', background: '#0A0A0A', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: 'linear-gradient(90deg, #C9A84C, #E2C47A, #C9A84C)' }} />

      <div style={{ padding: '20px 24px 0' }}>
        <button onClick={() => navigate(-1)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
      </div>

      <div style={{ padding: '24px 24px 40px' }}>
        <div style={{
          width: 64, height: 64, borderRadius: 16,
          background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24,
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
            <polyline points="22,6 12,13 2,6" />
          </svg>
        </div>

        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>
          Verificar email
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6 }}>
          Enviámos um código de 6 dígitos para{' '}
          <span style={{ color: '#C9A84C', fontWeight: 600 }}>{email}</span>
        </p>
      </div>

      <div style={{ padding: '0 24px' }}>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginBottom: 24 }}>
          {digits.map((d, i) => (
            <input key={i} ref={el => (inputs.current[i] = el)}
              type="tel" maxLength={1} value={d}
              onChange={e => handleDigit(i, e.target.value)}
              onKeyDown={e => handleKeyDown(i, e)}
              onPaste={handlePaste}
              style={{
                width: 46, height: 56, textAlign: 'center',
                fontSize: 22, fontWeight: 700,
                fontFamily: "'DM Sans', sans-serif",
                background: d ? 'rgba(201,168,76,0.08)' : '#1E1E1E',
                border: `2px solid ${d ? '#C9A84C' : '#2A2A2A'}`,
                borderRadius: 12, color: '#FFFFFF', outline: 'none',
                caretColor: '#C9A84C', transition: 'all 0.15s ease',
              }} />
          ))}
        </div>

        {error && (
          <div style={{
            padding: '12px 16px', borderRadius: 12, marginBottom: 16,
            background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)',
            fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#F87171', textAlign: 'center',
          }}>
            {error}
          </div>
        )}

        <button className="btn-primary" onClick={handleVerify}
          disabled={!filled || loading} style={{ opacity: filled && !loading ? 1 : 0.4 }}>
          {loading ? 'A verificar...' : 'Verificar'}
        </button>

        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>
            Não recebeu o email?{' '}
          </span>
          <button onClick={handleResend} disabled={!canResend}
            style={{
              fontFamily: "'DM Sans', sans-serif", fontSize: 13,
              color: canResend ? '#C9A84C' : '#9A9A9A',
              background: 'none', border: 'none', cursor: canResend ? 'pointer' : 'default',
            }}>
            {canResend ? 'Reenviar' : `Reenviar em ${countdown}s`}
          </button>
        </div>
      </div>
    </div>
  )
}
