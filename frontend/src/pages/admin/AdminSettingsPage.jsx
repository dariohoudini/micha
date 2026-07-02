import { useState, useEffect } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'
import { asList } from '@/lib/asList'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444'

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState({
    platform_commission: 10,
    min_payout_amount: 5000,
    express_delivery_radius_km: 30,
    max_session_count: 5,
    maintenance_mode: false,
    current_tc_version: '1.0',
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [announcements, setAnnouncements] = useState([])
  const [newAnn, setNewAnn] = useState({ title: '', message: '', type: 'info' })
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  useEffect(() => {
    // Real backends: the versioned KV settings store (admin-console) and
    // the admin announcements manager. This page previously PATCHed
    // /admin-api/settings/ (never existed → every save failed) and listed
    // the PUBLIC announcements endpoint.
    client.get('/api/v1/admin-console/settings/')
      .then(r => {
        const rows = asList(r.data, 'settings')
        setSettings(prev => {
          const merged = { ...prev }
          for (const row of rows) {
            if (row && row.key in merged && row.value !== undefined && row.value !== null) {
              merged[row.key] = row.value
            }
          }
          return merged
        })
      })
      .catch(() => {})
    client.get('/api/v1/collections/admin/announcements/')
      .then(r => setAnnouncements(asList(r.data, 'announcements')))
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      // The settings store is key/value (one POST per key, versioned with
      // history server-side).
      for (const [key, value] of Object.entries(settings)) {
        await client.post('/api/v1/admin-console/settings/', { key, value })
      }
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch { showToast('Erro ao guardar', 'error') }
    setSaving(false)
  }

  const createAnnouncement = async () => {
    if (!newAnn.title || !newAnn.message) return
    try {
      const res = await client.post('/api/v1/collections/admin/announcements/', newAnn)
      setAnnouncements(prev => [res.data, ...prev])
      setNewAnn({ title: '', message: '', type: 'info' })
      showToast('Anúncio publicado!')
    } catch { showToast('Erro ao publicar', 'error') }
  }

  const S = { fontFamily: "'DM Sans'", fontSize: 13, color: TEXT }

  return (
    <AdminLayout title="Definições">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, ...S }}>{toast.msg}</div>}

        <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 20px' }}>Definições da Plataforma</h1>

        {/* Platform settings */}
        <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 16, marginBottom: 16 }}>
          <h3 style={{ ...S, fontWeight: 600, margin: '0 0 14px' }}>Configuração geral</h3>
          {[
            { key: 'platform_commission', label: 'Comissão da plataforma (%)', type: 'number', min: 0, max: 50 },
            { key: 'min_payout_amount', label: 'Valor mínimo de pagamento (Kz)', type: 'number', min: 0 },
            { key: 'express_delivery_radius_km', label: 'Raio de entrega express (km)', type: 'number', min: 1 },
            { key: 'max_session_count', label: 'Sessões simultâneas máximas', type: 'number', min: 1, max: 20 },
            { key: 'current_tc_version', label: 'Versão dos Termos & Condições', type: 'text' },
          ].map(field => (
            <div key={field.key} style={{ marginBottom: 12 }}>
              <p style={{ ...S, fontSize: 11, color: MUTED, margin: '0 0 5px' }}>{field.label}</p>
              <input type={field.type} value={settings[field.key]} min={field.min} max={field.max}
                onChange={e => setSettings(p => ({ ...p, [field.key]: field.type === 'number' ? Number(e.target.value) : e.target.value }))}
                style={{ width: '100%', padding: '10px 12px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 8, color: TEXT, ...S, outline: 'none', boxSizing: 'border-box' }} />
            </div>
          ))}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <p style={{ ...S, fontWeight: 500, margin: '0 0 2px' }}>Modo de manutenção</p>
              <p style={{ ...S, fontSize: 11, color: MUTED, margin: 0 }}>Bloqueia o acesso à plataforma para utilizadores</p>
            </div>
            <button onClick={() => setSettings(p => ({ ...p, maintenance_mode: !p.maintenance_mode }))} style={{ width: 44, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer', background: settings.maintenance_mode ? RED : BORDER, position: 'relative', padding: 0 }}>
              <div style={{ width: 18, height: 18, borderRadius: '50%', background: TEXT, position: 'absolute', top: 3, left: settings.maintenance_mode ? 23 : 3, transition: 'left 0.2s' }} />
            </button>
          </div>

          <button onClick={handleSave} disabled={saving} style={{ width: '100%', padding: 13, borderRadius: 12, border: 'none', background: saved ? GREEN : G, color: saved ? TEXT : '#000', ...S, fontWeight: 600, cursor: 'pointer' }}>
            {saving ? 'A guardar...' : saved ? '✓ Guardado' : 'Guardar definições'}
          </button>
        </div>

        {/* Announcements */}
        <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 16 }}>
          <h3 style={{ ...S, fontWeight: 600, margin: '0 0 14px' }}>Anúncios da plataforma</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
            <input value={newAnn.title} onChange={e => setNewAnn(p => ({ ...p, title: e.target.value }))} placeholder="Título do anúncio" style={{ padding: '10px 12px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 8, color: TEXT, ...S, outline: 'none' }} />
            <textarea value={newAnn.message} onChange={e => setNewAnn(p => ({ ...p, message: e.target.value }))} placeholder="Mensagem..." rows={3} style={{ padding: '10px 12px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 8, color: TEXT, ...S, outline: 'none', resize: 'none' }} />
            <select value={newAnn.type} onChange={e => setNewAnn(p => ({ ...p, type: e.target.value }))} style={{ padding: '10px 12px', background: BG, border: `1px solid ${BORDER}`, borderRadius: 8, color: TEXT, ...S, outline: 'none' }}>
              <option value="info">Informação</option>
              <option value="warning">Aviso</option>
              <option value="promo">Promoção</option>
            </select>
            <button onClick={createAnnouncement} style={{ padding: '11px', borderRadius: 10, border: 'none', background: G, color: '#000', ...S, fontWeight: 600, cursor: 'pointer' }}>
              📢 Publicar anúncio
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {announcements.slice(0, 5).map(a => (
              <div key={a.id} style={{ padding: '10px 12px', background: BG, borderRadius: 8, border: `1px solid ${BORDER}` }}>
                <p style={{ ...S, fontWeight: 600, margin: '0 0 2px' }}>{a.title}</p>
                <p style={{ ...S, fontSize: 12, color: MUTED, margin: 0 }}>{a.message}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
