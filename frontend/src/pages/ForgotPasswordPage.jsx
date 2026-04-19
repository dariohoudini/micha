import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI } from '@/api/auth'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  const handleSubmit = async () => {
    if (!email.trim() || !email.includes('@')) { setError('Insira um email válido.'); return }
    setLoading(true)
    try {
      await authAPI.forgotPassword(email.toLowerCase().trim())
      setSent(true)
    } catch {
      setError('Não foi possível enviar o código. Verifique o email.')
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div style={{
        minHeight: '100%', background: '#0A0A0A',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '0 32px', textAlign: 'center',
      }}>
        <div style={{
          width: 80, height: 80, borderRadius: 20,
          background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 28,
        }}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
            stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </div>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>
          Código enviado
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6, marginBottom: 36 }}>
          Se este email existir na nossa base de dados, receberá um código de verificação em{' '}
          <span style={{ color: '#C9A84C' }}>{email}</span>.
        </p>
        <button className="btn-primary"
          onClick={() => navigate('/otp', { state: { email: email.toLowerCase().trim(), context: 'reset' } })}>
          Inserir código
        </button>
        <button onClick={() => navigate('/login')}
          style={{ marginTop: 16, fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', background: 'none', border: 'none', cursor: 'pointer' }}>
          Voltar ao início de sessão
        </button>
      </div>
    )
  }

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

      <div style={{ padding: '28px 24px 0' }}>
        <div style={{
          width: 64, height: 64, borderRadius: 16,
          background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24,
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>

        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>
          Recuperar acesso
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6, marginBottom: 32 }}>
          Insira o seu email e enviaremos um código para redefinir a sua palavra-passe.
        </p>

        {error && (
          <div style={{ padding: '12px 16px', borderRadius: 12, marginBottom: 16, background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#F87171' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 24 }}>
          <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Email
          </label>
          <input className="input-base" type="email" placeholder="o.seu@email.com"
            value={email} onChange={e => { setEmail(e.target.value); setError('') }}
            autoCapitalize="none" autoCorrect="off" />
        </div>

        <button className="btn-primary" onClick={handleSubmit} disabled={loading} style={{ opacity: loading ? 0.7 : 1 }}>
          {loading ? 'A enviar...' : 'Enviar código'}
        </button>
      </div>
    </div>
  )
}
