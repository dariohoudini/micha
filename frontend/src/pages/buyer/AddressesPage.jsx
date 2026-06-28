import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * AddressesPage — User Process Flow Chapter 9.2 + 11.5.
 *
 * Backed by `/api/v1/shipping/addresses/` (ShippingAddress model
 * which is already in the schema). All mutations log to UserEvent.
 *
 * Spec features wired here
 * ────────────────────────
 *  • List saved addresses with default marker
 *  • Add / Edit form with all spec fields
 *  • Set-as-default toggle (PATCH)
 *  • Delete with confirmation
 *  • "Use my location" button — tries the Geolocation API and
 *    auto-fills province/city via a reverse-geocode endpoint when
 *    available. Silently no-ops if permission denied.
 */

const PROVINCES = ['Luanda','Benguela','Huambo','Huíla','Cabinda','Uíge','Namibe','Malanje','Bié','Cuanza Norte','Cuanza Sul']

const S = { fontFamily: "'DM Sans', sans-serif" }
const input = {
  width: '100%', background: '#141414', border: '1px solid #2A2A2A',
  borderRadius: 12, padding: '12px 14px', ...S, fontSize: 14,
  color: '#FFFFFF', outline: 'none', boxSizing: 'border-box',
}
const label = { ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }

const emptyForm = {
  label: 'Casa',
  full_name: '',
  phone: '',
  province: 'Luanda',
  city: '',
  address_line: '',
  postal_code: '',
  is_default: false,
}

export default function AddressesPage() {
  const navigate = useNavigate()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)  // form object or null
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState(null)

  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }
  const reload = () => client.get('/api/v1/shipping/addresses/').then(r => setList(r.data?.results || r.data || []))

  useEffect(() => {
    track('addresses.open', {})
    reload().finally(() => setLoading(false))
  }, [])

  const save = async () => {
    const f = editing
    if (!f.full_name.trim() || !f.phone.trim() || !f.city.trim() || (f.address_line || '').trim().length < 10) {
      show('Preencha nome, telefone, cidade e morada (mín 10 caracteres).', 'error'); return
    }
    setSaving(true)
    try {
      const body = { ...f }
      let res
      if (f.id) {
        res = await client.put(`/api/v1/shipping/addresses/${f.id}/`, body)
        track('addresses.updated', { address_id: f.id, is_default: f.is_default })
      } else {
        res = await client.post('/api/v1/shipping/addresses/', body)
        track('addresses.created', { address_id: res.data?.id, is_default: f.is_default })
      }
      await reload()
      setEditing(null)
      show(f.id ? 'Morada actualizada!' : 'Morada guardada!')
    } catch (err) {
      show(err.response?.data?.detail || 'Erro ao guardar.', 'error')
    } finally { setSaving(false) }
  }

  const del = async (a) => {
    if (!confirm('Eliminar esta morada?')) return
    try {
      await client.delete(`/api/v1/shipping/addresses/${a.id}/`)
      track('addresses.deleted', { address_id: a.id })
      await reload()
      show('Morada eliminada.')
    } catch { show('Erro ao eliminar.', 'error') }
  }

  const setDefault = async (a) => {
    try {
      await client.patch(`/api/v1/shipping/addresses/${a.id}/set-default/`)
      track('addresses.set_default', { address_id: a.id })
      await reload()
      show('Definida como padrão.')
    } catch { show('Erro.', 'error') }
  }

  // §9.2 [Use My Location] — Geolocation + best-effort reverse geocode.
  const useMyLocation = async () => {
    if (!navigator.geolocation) { show('Sem suporte GPS no dispositivo.', 'error'); return }
    track('addresses.use_location_requested', {})
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const { latitude: lat, longitude: lng } = pos.coords
      try {
        const res = await client.get(`/api/v1/shipping/geocode/reverse/?lat=${lat}&lng=${lng}`)
        const g = res.data || {}
        setEditing(f => ({
          ...f,
          province: g.province || f.province,
          city: g.city || f.city,
          address_line: g.address_line || f.address_line,
        }))
        track('addresses.use_location_filled', { lat, lng })
      } catch {
        // Backend may not have a reverse-geocoder yet — still log
        // the coords so we can offer a manual confirm.
        setEditing(f => ({ ...f, address_line: f.address_line ? f.address_line : `Lat ${lat.toFixed(5)}, Lng ${lng.toFixed(5)}` }))
        track('addresses.use_location_geocode_unavailable', {})
      }
    }, () => {
      show('Não foi possível obter a localização.', 'error')
      track('addresses.use_location_denied', {})
    }, { enableHighAccuracy: true, timeout: 8000 })
  }

  // ── Form view ───────────────────────────────────────────────────
  if (editing) {
    const f = editing
    return (
      <BuyerLayout>
        {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
        <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          <button onClick={() => setEditing(null)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', color: '#FFF', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>{f.id ? 'Editar morada' : 'Nova morada'}</h1>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 120px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={label}>Etiqueta</label>
            <div style={{ display: 'flex', gap: 6 }}>
              {['Casa', 'Trabalho', 'Outro'].map(l => (
                <button key={l} type="button" onClick={() => setEditing(x => ({ ...x, label: l }))}
                  style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: `1.5px solid ${f.label === l ? '#C9A84C' : '#2A2A2A'}`, background: f.label === l ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: f.label === l ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>{l}</button>
              ))}
            </div>
          </div>
          <div><label style={label}>Nome completo *</label>
            <input value={f.full_name} onChange={e => setEditing(x => ({ ...x, full_name: e.target.value }))} placeholder="Como aparece no BI" style={input} /></div>
          <div><label style={label}>Telefone *</label>
            <input value={f.phone} onChange={e => setEditing(x => ({ ...x, phone: e.target.value }))} placeholder="+244 9XX XXX XXX" style={input} /></div>
          <div><label style={label}>Província *</label>
            <select value={f.province} onChange={e => setEditing(x => ({ ...x, province: e.target.value }))} style={input}>
              {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
            </select></div>
          <div><label style={label}>Município / Cidade *</label>
            <input value={f.city} onChange={e => setEditing(x => ({ ...x, city: e.target.value }))} placeholder="Ex: Luanda" style={input} /></div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={label}>Morada *</span>
              <button type="button" onClick={useMyLocation}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', ...S, fontSize: 11, color: '#C9A84C', display: 'flex', alignItems: 'center', gap: 4 }}>
                📍 Usar a minha localização
              </button>
            </div>
            <textarea rows={3} value={f.address_line} onChange={e => setEditing(x => ({ ...x, address_line: e.target.value }))} placeholder="Rua, bairro, ponto de referência" style={{ ...input, resize: 'vertical' }} />
          </div>
          <div><label style={label}>Código postal (opcional)</label>
            <input value={f.postal_code || ''} onChange={e => setEditing(x => ({ ...x, postal_code: e.target.value }))} style={input} /></div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12 }}>
            <span style={{ ...S, fontSize: 13, color: '#FFF' }}>Definir como padrão</span>
            <button onClick={() => setEditing(x => ({ ...x, is_default: !x.is_default }))}
              style={{ width: 44, height: 24, borderRadius: 12, border: 'none', background: f.is_default ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer' }}>
              <div style={{ position: 'absolute', top: 2, left: f.is_default ? 22 : 2, width: 20, height: 20, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s' }} />
            </button>
          </div>
        </div>
        <div style={{ padding: '12px 16px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', borderTop: '1px solid #1A1A1A', background: '#0A0A0A', flexShrink: 0 }}>
          <button onClick={save} disabled={saving}
            style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: 'none', background: saving ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            {saving ? 'A guardar…' : (f.id ? 'Actualizar morada' : 'Guardar morada')}
          </button>
        </div>
      </BuyerLayout>
    )
  }

  // ── List view ───────────────────────────────────────────────────
  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>As minhas moradas</h1>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 100px' }}>
        {loading ? (
          <div style={{ height: 80, background: '#141414', borderRadius: 14 }} />
        ) : list.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14 }}>
            <p style={{ fontSize: 40, marginBottom: 10 }}>📍</p>
            <p style={{ ...S, fontSize: 14, color: '#FFF', marginBottom: 6 }}>Sem moradas guardadas</p>
            <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 14 }}>Adicione uma morada para acelerar a finalização da compra.</p>
            <button onClick={() => setEditing({ ...emptyForm, is_default: true })}
              style={{ padding: '11px 22px', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
              + Adicionar morada
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {list.map(a => (
              <div key={a.id} style={{ background: '#141414', border: `1px solid ${a.is_default ? 'rgba(201,168,76,0.4)' : '#1E1E1E'}`, borderRadius: 14, padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div>
                    <span style={{ ...S, fontSize: 10, fontWeight: 700, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{a.label}</span>
                    <p style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFF', marginTop: 2 }}>{a.full_name}</p>
                  </div>
                  {a.is_default && <span style={{ ...S, fontSize: 9, fontWeight: 700, color: '#C9A84C', background: 'rgba(201,168,76,0.12)', padding: '2px 8px', borderRadius: 10, letterSpacing: '0.04em' }}>PADRÃO</span>}
                </div>
                <p style={{ ...S, fontSize: 12, color: '#BFBFBF', lineHeight: 1.5 }}>{a.address_line}</p>
                <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>{a.city}, {a.province}</p>
                <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>📞 {a.phone}</p>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button onClick={() => setEditing({ ...a })}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 12, color: '#FFF', cursor: 'pointer' }}>Editar</button>
                  {!a.is_default && (
                    <button onClick={() => setDefault(a)}
                      style={{ flex: 1, padding: '8px 0', borderRadius: 10, border: '1px solid rgba(201,168,76,0.4)', background: 'transparent', ...S, fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>Padrão</button>
                  )}
                  <button onClick={() => del(a)}
                    style={{ width: 70, padding: '8px 0', borderRadius: 10, border: '1px solid rgba(220,38,38,0.3)', background: 'transparent', ...S, fontSize: 12, color: '#dc2626', cursor: 'pointer' }}>✕</button>
                </div>
              </div>
            ))}
            <button onClick={() => setEditing({ ...emptyForm, is_default: list.length === 0 })}
              style={{ marginTop: 4, padding: '12px 0', borderRadius: 12, border: '1.5px dashed #C9A84C', background: 'transparent', ...S, fontSize: 13, color: '#C9A84C', cursor: 'pointer' }}>
              + Adicionar morada
            </button>
          </div>
        )}
      </div>
    </BuyerLayout>
  )
}
