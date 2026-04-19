import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore as useAuth } from '@/stores/authStore'

export default function ProfileEditPage() {
  const navigate = useNavigate()
  const user = useAuth(s => s.user); const login = useAuth(s => s.login)
  const [form, setForm] = useState({
    full_name: '',
    username: user?.username || '',
    phone: '',
    city: '',
    bio: '',
  })
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleChange = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }))

  const handleSave = async () => {
    setLoading(true)
    // TODO: call authAPI profile update when backend ready
    await new Promise(r => setTimeout(r, 800))
    setSaved(true)
    setLoading(false)
    setTimeout(() => navigate('/profile'), 1200)
  }

  const Label = ({ children, optional }) => (
    <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
      {children}{optional && <span style={{ color: '#555', fontWeight: 400 }}> (opcional)</span>}
    </label>
  )

  const initial = user?.email?.[0]?.toUpperCase() || 'U'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => navigate('/profile')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Editar perfil</h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Avatar */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 0 16px' }}>
            <div style={{ position: 'relative' }}>
              <div style={{
                width: 84, height: 84, borderRadius: '50%',
                background: 'linear-gradient(135deg, #C9A84C, #A67C35)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 32, fontWeight: 700, color: '#0A0A0A' }}>{initial}</span>
              </div>
              <div style={{
                position: 'absolute', bottom: 0, right: 0,
                width: 26, height: 26, borderRadius: '50%',
                background: '#C9A84C', border: '2px solid #0A0A0A',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer',
              }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
              </div>
            </div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 10 }}>Toque para alterar a foto</p>
          </div>

          {/* Email (read only) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Email</Label>
            <div style={{ padding: '12px 16px', borderRadius: 12, background: '#141414', border: '1px solid #1E1E1E' }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>{user?.email}</span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Nome completo</Label>
            <input className="input-base" name="full_name" placeholder="João Silva"
              value={form.full_name} onChange={handleChange} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Username</Label>
            <input className="input-base" name="username" placeholder="joaosilva"
              value={form.username} onChange={handleChange} autoCapitalize="none" />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Telefone</Label>
            <div style={{ display: 'flex' }}>
              <div style={{ display: 'flex', alignItems: 'center', padding: '0 14px', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRight: 'none', borderRadius: '12px 0 0 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap' }}>
                🇦🇴 +244
              </div>
              <input className="input-base" name="phone" type="tel" placeholder="9xx xxx xxx"
                value={form.phone} onChange={handleChange} style={{ borderRadius: '0 12px 12px 0', flex: 1 }} />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Cidade</Label>
            <input className="input-base" name="city" placeholder="Luanda"
              value={form.city} onChange={handleChange} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Bio</Label>
            <textarea className="input-base" name="bio" placeholder="Conte um pouco sobre si..."
              value={form.bio} onChange={handleChange} rows={3} style={{ resize: 'none', lineHeight: 1.6 }} />
          </div>

          <button className="btn-primary" onClick={handleSave} disabled={loading}
            style={{ marginTop: 8, opacity: loading ? 0.7 : 1, background: saved ? '#059669' : '#C9A84C', transition: 'background 0.3s' }}>
            {saved ? 'Guardado!' : loading ? 'A guardar...' : 'Guardar alterações'}
          </button>
        </div>
      </div>
    </div>
  )
}
