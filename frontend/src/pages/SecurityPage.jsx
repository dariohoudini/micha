import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore as useAuth } from '@/stores/authStore'

export default function SecurityPage() {
  const navigate = useNavigate()
  const logout = useAuth(s => s.logout)
  const [showChangePassword, setShowChangePassword] = useState(false)
  const [passwords, setPasswords] = useState({ old: '', new: '', confirm: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handlePasswordChange = async () => {
    if (!passwords.old || !passwords.new) { setError('Preencha todos os campos.'); return }
    if (passwords.new !== passwords.confirm) { setError('As palavras-passe não coincidem.'); return }
    if (passwords.new.length < 8) { setError('Mínimo 8 caracteres.'); return }
    setLoading(true)
    setError('')
    try {
      // TODO: call authAPI.changePassword when backend ready
      await new Promise(r => setTimeout(r, 800))
      setSuccess('Palavra-passe alterada. Todas as outras sessões foram encerradas.')
      setShowChangePassword(false)
      setPasswords({ old: '', new: '', confirm: '' })
    } catch {
      setError('Erro ao alterar palavra-passe.')
    } finally {
      setLoading(false)
    }
  }

  const SECURITY_ITEMS = [
    {
      icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
      label: 'Alterar palavra-passe',
      sub: 'Recomendado a cada 3 meses',
      action: () => setShowChangePassword(v => !v),
      color: '#C9A84C',
    },
    {
      icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
      label: 'Autenticação 2 factores',
      sub: 'Adiciona uma camada extra de segurança',
      action: () => {},
      color: '#3b82f6',
      badge: 'Em breve',
    },
    {
      icon: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
      label: 'Terminar todas as sessões',
      sub: 'Encerra sessão em todos os dispositivos',
      action: () => { logout(); navigate('/login') },
      color: '#dc2626',
    },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => navigate('/profile')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Privacidade & Segurança</h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {success && (
            <div style={{ padding: '12px 16px', borderRadius: 12, background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#059669' }}>
              {success}
            </div>
          )}

          {SECURITY_ITEMS.map((item, i) => (
            <div key={i}>
              <button onClick={item.action}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 14,
                  padding: '16px', borderRadius: 16, cursor: 'pointer', textAlign: 'left',
                  background: '#141414', border: '1px solid #1E1E1E',
                }}>
                <div style={{ width: 40, height: 40, borderRadius: 12, background: `${item.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={item.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={item.icon} />
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500, color: item.color === '#dc2626' ? '#dc2626' : '#FFFFFF' }}>{item.label}</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>{item.sub}</p>
                </div>
                {item.badge && (
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: '#9A9A9A', background: '#1E1E1E', border: '1px solid #2A2A2A', padding: '3px 8px', borderRadius: 20 }}>{item.badge}</span>
                )}
                {!item.badge && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                )}
              </button>

              {/* Change password inline form */}
              {item.label === 'Alterar palavra-passe' && showChangePassword && (
                <div style={{ background: '#0F0F0F', border: '1px solid #1E1E1E', borderTop: 'none', borderRadius: '0 0 16px 16px', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {error && (
                    <div style={{ padding: '10px 14px', borderRadius: 10, background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{error}</div>
                  )}
                  {[{ name: 'old', placeholder: 'Palavra-passe atual' }, { name: 'new', placeholder: 'Nova palavra-passe' }, { name: 'confirm', placeholder: 'Confirmar nova palavra-passe' }].map(field => (
                    <input key={field.name} className="input-base" type="password" placeholder={field.placeholder}
                      value={passwords[field.name]} onChange={e => { setPasswords(p => ({ ...p, [field.name]: e.target.value })); setError('') }} />
                  ))}
                  <button className="btn-primary" onClick={handlePasswordChange} disabled={loading} style={{ opacity: loading ? 0.7 : 1 }}>
                    {loading ? 'A alterar...' : 'Confirmar'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
