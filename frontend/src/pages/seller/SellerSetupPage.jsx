import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

const PROVINCES = ['Luanda','Benguela','Huambo','Huíla','Cabinda','Uíge','Namibe','Malanje','Bié']

function ImageUploadField({ label, currentUrl, fieldName, onFile }) {
  const ref = useRef()
  const [preview, setPreview] = useState(null)
  const S = { fontFamily: "'DM Sans', sans-serif" }

  const handleChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    setPreview(url)
    onFile(fieldName, file)
  }

  const src = preview || currentUrl

  return (
    <div>
      <label style={{ ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }}>{label}</label>
      <button
        type="button"
        onClick={() => ref.current?.click()}
        style={{ width: '100%', height: fieldName === 'banner_image' ? 110 : 80, borderRadius: 12, border: '1.5px dashed #2A2A2A', background: '#141414', cursor: 'pointer', overflow: 'hidden', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        {src
          ? <img src={src} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.5" strokeLinecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
              <span style={{ ...S, fontSize: 11, color: '#555' }}>Carregar {label.toLowerCase()}</span>
            </div>
          )
        }
        {src && (
          <div style={{ position: 'absolute', bottom: 6, right: 6, background: 'rgba(0,0,0,0.7)', borderRadius: 6, padding: '3px 8px' }}>
            <span style={{ ...S, fontSize: 10, color: '#C9A84C' }}>Alterar</span>
          </div>
        )}
      </button>
      <input ref={ref} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleChange} />
    </div>
  )
}

export default function SellerSetupPage() {
  const navigate = useNavigate()
  // ── Two-model setup ─────────────────────────────────────────────
  // This page edits two distinct backend records simultaneously:
  //   1. Store           — name, description, city, banner_image,
  //                        primary_color, is_active, is_open.
  //                        Required for a seller to publish products
  //                        (apps/products/views.py ProductCreateView
  //                        looks up Store(owner=user)).
  //   2. SellerProfile   — store_logo, return_policy, shipping_policy,
  //                        working_hours, holiday flags, etc.
  //                        Cosmetic / policy metadata for the
  //                        public storefront.
  //
  // The UI presents them as one form for the seller's convenience;
  // the save handler dispatches to two endpoints in sequence. The
  // PRIOR implementation here only wrote SellerProfile via PUT and
  // never created/updated a Store at all — so "Save" looked like a
  // success but no Store row ever existed. That left sellers unable
  // to publish products and (worse) the toast lied about success.
  const [profile, setProfile] = useState({})        // SellerProfile + UI extras
  const [store, setStore] = useState(null)          // Store (null = none yet)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('store')
  const [toast, setToast] = useState(null)
  const [pendingFiles, setPendingFiles] = useState({})

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 2500) }

  useEffect(() => {
    // Load both records in parallel so the form opens populated.
    // .all-style Promise.all would reject if either fails; we let
    // them settle independently so a 404 on /seller/profile/ (rare,
    // but happens for users who landed here via a deep link before
    // the profile is auto-provisioned) doesn't blank the store
    // section too.
    Promise.allSettled([
      client.get('/api/v1/stores/my/'),
      client.get('/api/v1/seller/profile/'),
    ]).then(([storesRes, profileRes]) => {
      if (storesRes.status === 'fulfilled') {
        const list = storesRes.value.data?.results || storesRes.value.data || []
        // One store per seller for now (AliExpress-style single
        // storefront). If a seller ever ends up with multiple rows
        // — e.g. legacy seed data — we pick the most recent.
        const first = Array.isArray(list) ? list[0] : list
        if (first && first.id) {
          setStore(first)
          // Seed the form's "store" tab from the Store record.
          setProfile(prev => ({
            ...prev,
            store_name: first.name || '',
            description: first.description || '',
            province: first.city || 'Luanda',
            banner_image: first.banner_image || null,
          }))
        }
      }
      if (profileRes.status === 'fulfilled') {
        const p = profileRes.value.data || {}
        // Merge AFTER store seed so SellerProfile-only fields fill
        // in without overwriting Store-sourced fields with empty
        // values from the SellerProfile shape.
        setProfile(prev => ({
          ...prev,
          ...p,
          // Preserve store-sourced values that exist on both sides.
          store_name: prev.store_name || p.store_name || '',
          description: prev.description || p.description || '',
          province: prev.province || p.province || 'Luanda',
        }))
      }
    }).finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      // ── 1) Store: create on first save, PATCH on subsequent ────
      // Send FormData so banner_image (a File) goes through cleanly.
      const storeFd = new FormData()
      // Trim defaults so empty inputs don't overwrite real data
      // with whitespace.
      const storeName = (profile.store_name || '').trim()
      if (!storeName) {
        showToast('Dê um nome à sua loja para guardar.', 'error')
        setSaving(false)
        return
      }
      if (nameStatus === 'taken') {
        showToast('Esse nome já está em uso. Escolha outro.', 'error')
        setSaving(false)
        return
      }
      storeFd.append('name', storeName)
      if (profile.description) storeFd.append('description', profile.description.trim())
      if (profile.province) storeFd.append('city', profile.province)
      if (pendingFiles.banner_image) storeFd.append('banner_image', pendingFiles.banner_image)
      // Keep is_active/is_open defaults from the model unless the
      // seller toggled them somewhere (not exposed in this form
      // today; ToggleStoreOpenView handles open/closed runtime).

      let savedStore
      if (store?.id) {
        const res = await client.patch(
          `/api/v1/stores/my/${store.id}/`,
          storeFd,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        )
        savedStore = res.data
      } else {
        const res = await client.post(
          '/api/v1/stores/my/',
          storeFd,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        )
        savedStore = res.data
        setStore(savedStore)
      }

      // ── 2) SellerProfile: logo + policies + holiday flags ──────
      // The SellerProfile endpoint is RetrieveUpdate so PUT is fine
      // even on first call (the view get_or_create's the row).
      const profileFd = new FormData()
      // Only send fields that exist on SellerProfileSerializer —
      // anything else is silently dropped by DRF, but we filter
      // explicitly so it's obvious which fields are persistable.
      const PROFILE_KEYS = [
        'return_policy', 'shipping_policy',
        'is_on_holiday', 'holiday_message', 'holiday_until',
        'revenue_goal', 'subscription_plan',
      ]
      for (const k of PROFILE_KEYS) {
        const v = profile[k]
        if (v !== null && v !== undefined && v !== '') profileFd.append(k, v)
      }
      if (pendingFiles.logo) profileFd.append('store_logo', pendingFiles.logo)
      // banner_image goes to Store (above) — SellerProfile.store_banner
      // is the legacy field; keep Store as the canonical place.

      await client.put(
        '/api/v1/seller/profile/',
        profileFd,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )

      setPendingFiles({})
      showToast('Loja guardada!')
      // Navigate to the dedicated "Minha Loja" screen — AliExpress
      // §7.2 / §8.1 mandate that the very next view after a save
      // SHOWS the store (banner, name, status, CTAs). The generic
      // /seller dashboard buries this, so we go to /seller/store.
      // `justSaved: true` triggers the green confirmation banner.
      setTimeout(() => navigate('/seller/store', { state: { justSaved: true } }), 600)
    } catch (err) {
      const data = err.response?.data
      let msg = 'Erro ao guardar.'
      if (data && typeof data === 'object') {
        if (typeof data.detail === 'string') msg = data.detail
        else {
          const skip = new Set(['request_id', 'trace_id', 'code', 'status'])
          for (const [k, v] of Object.entries(data)) {
            if (skip.has(k)) continue
            const val = Array.isArray(v) ? v[0] : v
            if (typeof val === 'string' && val.trim()) {
              msg = `${k}: ${val}`
              break
            }
          }
        }
      }
      showToast(msg, 'error')
    }
    finally { setSaving(false) }
  }

  const update = (field, value) => setProfile(prev => ({ ...prev, [field]: value }))
  const addFile = (field, file) => setPendingFiles(prev => ({ ...prev, [field]: file }))

  // ── §5.3 store-name availability check ────────────────────────
  // Spec: 800ms after the seller stops typing, query the backend
  // for name conflicts. Backend currently exposes /api/v1/stores/?search=
  // (public store list with search) — close enough; we treat any
  // exact-name match from a different store_id as taken.
  const [nameStatus, setNameStatus] = useState('idle') // idle|checking|available|taken
  useEffect(() => {
    const name = (profile.store_name || '').trim()
    if (name.length < 3) { setNameStatus('idle'); return }
    if (store && store.name === name) { setNameStatus('available'); return }
    setNameStatus('checking')
    const t = setTimeout(() => {
      client.get(`/api/v1/stores/?search=${encodeURIComponent(name)}`)
        .then(res => {
          const list = res.data?.results || res.data || []
          const taken = (Array.isArray(list) ? list : [])
            .some(s => (s.name || '').toLowerCase() === name.toLowerCase()
                       && (!store || s.id !== store.id))
          setNameStatus(taken ? 'taken' : 'available')
        })
        .catch(() => setNameStatus('idle'))
    }, 800)
    return () => clearTimeout(t)
  }, [profile.store_name, store])
  const S = { fontFamily: "'DM Sans', sans-serif" }
  const inputStyle = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 13, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }
  const labelStyle = { ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }

  return (
    <SellerLayout title="Configurações da Loja">
      {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#fff', padding: '10px 20px', borderRadius: 12, ...S, fontSize: 13, whiteSpace: 'nowrap' }}>{toast.msg}</div>}

      <div style={{ display: 'flex', borderBottom: '1px solid #1E1E1E', flexShrink: 0 }}>
        {[{v:'store',l:'Loja'},{v:'media',l:'Imagens'},{v:'contact',l:'Contacto'},{v:'policies',l:'Políticas'}].map(tab => (
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
              <div>
                <label style={labelStyle}>Nome da loja</label>
                <input
                  value={profile.store_name || ''}
                  onChange={e => update('store_name', e.target.value)}
                  placeholder="Ex: Capulanas da Maria"
                  style={{
                    ...inputStyle,
                    borderColor: nameStatus === 'taken' ? '#ef4444'
                      : nameStatus === 'available' ? '#10b981'
                      : '#2A2A2A',
                  }}
                />
                {/* §5.3 — live availability hint */}
                <p style={{ ...S, fontSize: 11, marginTop: 6,
                  color: nameStatus === 'taken' ? '#ef4444'
                    : nameStatus === 'available' ? '#10b981'
                    : nameStatus === 'checking' ? '#9A9A9A'
                    : '#555',
                }}>
                  {nameStatus === 'checking' && '⏳ A verificar disponibilidade…'}
                  {nameStatus === 'available' && '✓ Nome disponível'}
                  {nameStatus === 'taken' && '✗ Nome já em uso. Experimente outro.'}
                  {nameStatus === 'idle' && (profile.store_name || '').length > 0 && (profile.store_name || '').length < 3 && 'Mínimo 3 caracteres'}
                </p>
              </div>
              <div>
                <label style={labelStyle}>Slogan</label>
                <input value={profile.tagline || ''} onChange={e => update('tagline', e.target.value)} placeholder="Ex: A melhor moda angolana" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Descrição</label>
                <textarea
                  value={profile.description || ''}
                  onChange={e => update('description', e.target.value)}
                  placeholder="Descreva a sua loja..."
                  rows={3}
                  maxLength={2000}
                  style={{ ...inputStyle, resize: 'vertical' }}
                />
                {/* §5.2 — char counter, min 50 / max 2000 */}
                <p style={{ ...S, fontSize: 11, marginTop: 6,
                  color: (profile.description || '').length < 50 ? '#f59e0b' : '#9A9A9A',
                }}>
                  {(profile.description || '').length} / 2000
                  {(profile.description || '').length < 50 && ' · mínimo 50 caracteres recomendado'}
                </p>
              </div>
              <div>
                <label style={labelStyle}>Província</label>
                <select value={profile.province || 'Luanda'} onChange={e => update('province', e.target.value)} style={inputStyle}>
                  {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </>}

            {activeTab === 'media' && <>
              <ImageUploadField
                label="Banner da loja"
                fieldName="banner_image"
                currentUrl={profile.banner_image}
                onFile={addFile}
              />
              <ImageUploadField
                label="Logótipo"
                fieldName="logo"
                currentUrl={profile.logo}
                onFile={addFile}
              />
              <p style={{ ...S, fontSize: 11, color: '#555', marginTop: 4, lineHeight: 1.6 }}>
                Recomendado: banner 1200×400px · logótipo 400×400px. Formatos: JPG, PNG, WEBP.
              </p>
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
