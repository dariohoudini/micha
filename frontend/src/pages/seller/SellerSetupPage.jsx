import { useState, useEffect } from 'react'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

const PROVINCES = ['Luanda','Benguela','Huambo','Huíla','Cabinda','Uíge','Namibe','Malanje','Bié']

export default function SellerSetupPage() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('store')
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 2500) }

  useEffect(() => {
    client.get('/api/v1/seller/profile/')
      .then(res => setProfile(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const formData = new FormData()
      Object.entries(profile || {}).forEach(([k, v]) => {
        if (v !== null && v !== undefined && typeof v !== 'object') formData.append(k, v)
      })
      await client.put('/api/v1/seller/profile/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      showToast('Perfil actualizado!')
    } catch { showToast('Erro ao guardar.', 'error') }
    finally { setSaving(false) }
  }

  const update = (field, value) => setProfile(prev => ({ ...prev, [field]: value }))
  const S = { fontFamily: "'DM Sans', sans-serif" }
  const inputStyle = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 13, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }
  const labelStyle = { ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }

  return (
    <SellerLayout title="Configurações da Loja">
      {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#fff', padding: '10px 20px', borderRadius: 12, ...S, fontSize: 13, whiteSpace: 'nowrap' }}>{toast.msg}</div>}

      <div style={{ display: 'flex', borderBottom: '1px solid #1E1E1E', flexShrink: 0 }}>
        {[{v:'store',l:'Loja'},{v:'contact',l:'Contacto'},{v:'policies',l:'Políticas'}].map(tab => (
          <button key={tab.v} onClick={() => setActiveTab(tab.v)}
            style={{ flex: 1, padding: '12px 0', background: 'none', border: 'none', cursor: 'pointer', ...S, fontSize: 13, fontWeight: activeTab === tab.v ? 600 : 400, color: activeTab === tab.v ? '#C9A84C' : '#9A9A9A', borderBottom: `2px solid ${activeTab === tab.v ? '#C9A84C' : 'transparent'}`, marginBottom: -1 }}>
            {tab.l}
          </button>
        ))}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}><style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style></div>
          </div>
        ) : profile && (
          <div style={{ padding: '16px 16px 100px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {activeTab === 'store' && <>
              {[
                { f: 'store_name', l: 'Nome da loja', p: 'Ex: Capulanas da Maria' },
                { f: 'tagline', l: 'Slogan', p: 'Ex: A melhor moda angolana' },
              ].map(field => (
                <div key={field.f}>
                  <label style={labelStyle}>{field.l}</label>
                  <input value={profile[field.f] || ''} onChange={e => update(field.f, e.target.value)} placeholder={field.p} style={inputStyle} />
                </div>
              ))}
              <div>
                <label style={labelStyle}>Descrição</label>
                <textarea value={profile.description || ''} onChange={e => update('description', e.target.value)} placeholder="Descreva a sua loja..." rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
              </div>
              <div>
                <label style={labelStyle}>Província</label>
                <select value={profile.province || 'Luanda'} onChange={e => update('province', e.target.value)} style={inputStyle}>
                  {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </>}
            {activeTab === 'contact' && <>
              {[{f:'phone',l:'Telefone',p:'+244 9XX XXX XXX'},{f:'whatsapp',l:'WhatsApp',p:'+244 9XX XXX XXX'},{f:'address',l:'Morada',p:'Rua, Bairro, Município'}].map(field => (
                <div key={field.f}>
                  <label style={labelStyle}>{field.l}</label>
                  <input value={profile[field.f] || ''} onChange={e => update(field.f, e.target.value)} placeholder={field.p} style={inputStyle} />
                </div>
              ))}
            </>}
            {activeTab === 'policies' && <>
              {[{f:'return_policy',l:'Política de devoluções',p:'Ex: Devoluções aceites em 15 dias...'},{f:'shipping_policy',l:'Política de envio',p:'Ex: Envio em 1-2 dias úteis...'}].map(field => (
                <div key={field.f}>
                  <label style={labelStyle}>{field.l}</label>
                  <textarea value={profile[field.f] || ''} onChange={e => update(field.f, e.target.value)} placeholder={field.p} rows={4} style={{ ...inputStyle, resize: 'vertical' }} />
                </div>
              ))}
            </>}
          </div>
        )}
      </div>

      <div style={{ padding: '14px 16px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
        <button onClick={handleSave} disabled={saving}
          style={{ width: '100%', padding: '15px 0', borderRadius: 14, border: 'none', background: saving ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          {saving ? 'A guardar...' : 'Guardar alterações'}
        </button>
      </div>
    </SellerLayout>
  )
}
