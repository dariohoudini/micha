import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { authAPI } from '@/api/auth'
import { toast } from '@/components/ui/Toast'

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const email = location.state?.email || ''
  const otp = location.state?.otp || ''

  const [form, setForm] = useState({ new_password: '', confirm: '' })
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    if (form.new_password.length < 8) { setError('Mínimo 8 caracteres.'); return }
    if (form.new_password !== form.confirm) { setError('As palavras-passe não coincidem.'); return }
    setLoading(true)
    try {
      await authAPI.resetPassword(email, otp, form.new_password)
      toast.success('Palavra-passe redefinida com sucesso!')
      navigate('/login')
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao redefinir palavra-passe.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100%', background: '#0A0A0A', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: 'linear-gradient(90deg, #C9A84C, #E2C47A, #C9A84C)' }} />

      <div style={{ padding: '20px 24px 0' }}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
      </div>

      <div style={{ padding: '24px 24px 0' }}>
        <div style={{ width: 64, height: 64, borderRadius: 16, background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>

        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>Nova palavra-passe</h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6, marginBottom: 28 }}>
          Escolha uma nova palavra-passe para a sua conta.
        </p>

        {error && (
          <div style={{ padding: '12px 16px', borderRadius: 12, marginBottom: 16, background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#F87171' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Nova palavra-passe</label>
            <div style={{ position: 'relative' }}>
              <input className="input-base" type={show ? 'text' : 'password'} placeholder="Mínimo 8 caracteres"
                value={form.new_password} onChange={e => { setForm(f => ({ ...f, new_password: e.target.value })); setError('') }}
                style={{ paddingRight: 48 }} />
              <button onClick={() => setShow(v => !v)} style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={show ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                </svg>
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Confirmar palavra-passe</label>
            <input className="input-base" type="password" placeholder="••••••••"
              value={form.confirm} onChange={e => { setForm(f => ({ ...f, confirm: e.target.value })); setError('') }} />
          </div>

          <button className="btn-primary" onClick={handleSubmit} disabled={loading} style={{ marginTop: 8, opacity: loading ? 0.7 : 1 }}>
            {loading ? 'A guardar...' : 'Guardar nova palavra-passe'}
          </button>
        </div>
      </div>
    </div>
  )
}
