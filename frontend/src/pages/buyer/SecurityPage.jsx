import { useState } from 'react'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const GOLD = '#C9A84C', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A', GREEN = '#059669', RED = '#EF4444'

export default function SecurityPage() {
  const [form, setForm] = useState({ old_password: '', new_password: '', new_password2: '' })
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)
  const [showPwd, setShowPwd] = useState(false)

  const handleChange = e => setForm(p => ({ ...p, [e.target.name]: e.target.value }))

  const handleSubmit = async () => {
    if (form.new_password !== form.new_password2) { setMsg({ text: 'As palavras-passe não coincidem', type: 'error' }); return }
    setLoading(true)
    try {
      await client.post('/api/v1/auth/change-password/', form)
      setMsg({ text: 'Palavra-passe alterada com sucesso', type: 'success' })
      setForm({ old_password: '', new_password: '', new_password2: '' })
    } catch (e) {
      setMsg({ text: e.response?.data?.detail || 'Erro ao alterar palavra-passe', type: 'error' })
    }
    setLoading(false)
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <BuyerLayout title="Segurança">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        <h1 style={{ ...S, fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: TEXT, margin: '0 0 24px' }}>Segurança da conta</h1>

        {msg && (
          <div style={{ padding: '12px 14px', borderRadius: 10, background: msg.type === 'success' ? 'rgba(5,150,105,0.1)' : 'rgba(239,68,68,0.1)', border: `1px solid ${msg.type === 'success' ? GREEN : RED}`, marginBottom: 16 }}>
            <p style={{ ...S, fontSize: 13, color: msg.type === 'success' ? GREEN : RED, margin: 0 }}>{msg.text}</p>
          </div>
        )}

        <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <p style={{ ...S, fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Alterar palavra-passe</p>

          {[
            { name: 'old_password', label: 'Palavra-passe actual' },
            { name: 'new_password', label: 'Nova palavra-passe' },
            { name: 'new_password2', label: 'Confirmar nova palavra-passe' },
          ].map(field => (
            <div key={field.name}>
              <p style={{ ...S, fontSize: 12, color: MUTED, margin: '0 0 6px' }}>{field.label}</p>
              <div style={{ position: 'relative' }}>
                <input
                  name={field.name}
                  type={showPwd ? 'text' : 'password'}
                  value={form[field.name]}
                  onChange={handleChange}
                  style={{ width: '100%', padding: '12px 44px 12px 14px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 10, color: TEXT, ...S, fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
                />
                <button onClick={() => setShowPwd(!showPwd)} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: MUTED }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    {showPwd ? <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></> : <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>}
                  </svg>
                </button>
              </div>
            </div>
          ))}

          <button onClick={handleSubmit} disabled={loading} style={{ padding: 13, borderRadius: 12, border: 'none', background: GOLD, color: '#000', ...S, fontSize: 14, fontWeight: 600, cursor: 'pointer', opacity: loading ? 0.7 : 1 }}>
            {loading ? 'A guardar...' : 'Alterar palavra-passe'}
          </button>
        </div>
      </div>
    </BuyerLayout>
  )
}
