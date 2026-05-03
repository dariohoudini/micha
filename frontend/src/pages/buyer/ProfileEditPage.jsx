import { useState, useEffect } from 'react'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const GOLD = '#C9A84C', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A', GREEN = '#059669'

const PROVINCES = ['Luanda','Benguela','Huambo','Huíla','Cabinda','Malanje','Uíge','Kuanza Norte','Kuanza Sul','Bié','Moxico','Cuando Cubango','Cunene','Namibe','Zaire','Lunda Norte','Lunda Sul','Bengo']

export default function ProfileEditPage() {
  const [form, setForm] = useState({ full_name: '', phone: '', province: '', bio: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    client.get('/api/v1/auth/profile/').then(r => {
      const d = r.data
      setForm({ full_name: d.full_name || '', phone: d.phone || '', province: d.province || '', bio: d.bio || '' })
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await client.patch('/api/v1/auth/profile/update/', form)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {}
    setSaving(false)
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }
  const fields = [
    { key: 'full_name', label: 'Nome completo', type: 'text', placeholder: 'António Cabaço' },
    { key: 'phone', label: 'Telemóvel', type: 'tel', placeholder: '+244 923 000 000' },
    { key: 'bio', label: 'Bio', type: 'text', placeholder: 'Conta-nos um pouco sobre ti...' },
  ]

  return (
    <BuyerLayout title="Editar perfil">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        <h1 style={{ ...S, fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: TEXT, margin: '0 0 24px' }}>Editar perfil</h1>

        <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {fields.map(f => (
            <div key={f.key}>
              <p style={{ ...S, fontSize: 12, color: MUTED, margin: '0 0 6px' }}>{f.label}</p>
              <input type={f.type} value={form[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} placeholder={f.placeholder}
                style={{ width: '100%', padding: '12px 14px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 10, color: TEXT, ...S, fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
            </div>
          ))}

          <div>
            <p style={{ ...S, fontSize: 12, color: MUTED, margin: '0 0 6px' }}>Província</p>
            <select value={form.province} onChange={e => setForm(p => ({ ...p, province: e.target.value }))}
              style={{ width: '100%', padding: '12px 14px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 10, color: form.province ? TEXT : MUTED, ...S, fontSize: 14, outline: 'none', boxSizing: 'border-box' }}>
              <option value="">Selecciona a tua província</option>
              {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          <button onClick={handleSave} disabled={saving} style={{ padding: 13, borderRadius: 12, border: 'none', background: saved ? GREEN : GOLD, color: saved ? TEXT : '#000', ...S, fontSize: 14, fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}>
            {saving ? 'A guardar...' : saved ? '✓ Guardado' : 'Guardar alterações'}
          </button>
        </div>
      </div>
    </BuyerLayout>
  )
}
