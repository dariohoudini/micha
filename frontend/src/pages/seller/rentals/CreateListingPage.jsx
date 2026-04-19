import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

const STEPS = [
  { n: 1, label: 'Tipo & Função' },
  { n: 2, label: 'Detalhes' },
  { n: 3, label: 'Localização' },
  { n: 4, label: 'Preço' },
  { n: 5, label: 'Fotos' },
  { n: 6, label: 'Revisão' },
]

const PROPERTY_TYPES = [
  { v: 'apartment', l: 'Apartamento', icon: '🏢' },
  { v: 'house', l: 'Vivenda', icon: '🏠' },
  { v: 'room', l: 'Quarto', icon: '🛏' },
  { v: 'office', l: 'Escritório', icon: '💼' },
  { v: 'warehouse', l: 'Armazém', icon: '🏭' },
  { v: 'land', l: 'Terreno', icon: '🌿' },
  { v: 'commercial', l: 'Comercial', icon: '🏪' },
  { v: 'villa', l: 'Condomínio', icon: '🏰' },
]

const VEHICLE_TYPES = [
  { v: 'car', l: 'Automóvel', icon: '🚗' },
  { v: 'suv', l: 'SUV / 4x4', icon: '🚙' },
  { v: 'pickup', l: 'Pickup', icon: '🛻' },
  { v: 'motorcycle', l: 'Motociclo', icon: '🏍' },
  { v: 'truck', l: 'Camião', icon: '🚚' },
  { v: 'minibus', l: 'Minibus', icon: '🚐' },
]

const AMENITIES = [
  { v: 'water_24h', l: 'Água 24h' }, { v: 'generator', l: 'Gerador' },
  { v: 'security', l: 'Segurança' }, { v: 'pool', l: 'Piscina' },
  { v: 'gym', l: 'Ginásio' }, { v: 'parking', l: 'Estacionamento' },
  { v: 'garden', l: 'Jardim' }, { v: 'elevator', l: 'Elevador' },
  { v: 'internet', l: 'Internet' }, { v: 'air_conditioning', l: 'Ar Condicionado' },
  { v: 'solar_panels', l: 'Painéis Solares' }, { v: 'satellite_tv', l: 'TV Satélite' },
  { v: 'cctv', l: 'CCTV' }, { v: 'pets_allowed', l: 'Animais Permitidos' },
  { v: 'furnished_kitchen', l: 'Cozinha Equipada' }, { v: 'laundry', l: 'Lavandaria' },
]

const PROVINCES = [
  'Luanda', 'Benguela', 'Huambo', 'Huíla', 'Cabinda', 'Uíge',
  'Namibe', 'Malanje', 'Bié', 'Moxico', 'Cunene', 'Cuando Cubango',
  'Lunda Norte', 'Lunda Sul', 'Kwanza Norte', 'Kwanza Sul', 'Bengo', 'Zaire',
]

function Counter({ label, value, onChange, min = 0, max = 20 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid #1E1E1E' }}>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: '#1E1E1E', borderRadius: 10, border: '1px solid #2A2A2A', overflow: 'hidden' }}>
        <button onClick={() => onChange(Math.max(min, value - 1))}
          style={{ width: 36, height: 36, background: 'none', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 18 }}>−</button>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 600, color: '#FFFFFF', minWidth: 28, textAlign: 'center' }}>{value}</span>
        <button onClick={() => onChange(Math.min(max, value + 1))}
          style={{ width: 36, height: 36, background: 'none', border: 'none', cursor: 'pointer', color: '#FFFFFF', fontSize: 18 }}>+</button>
      </div>
    </div>
  )
}

export default function CreateListingPage() {
  const navigate = useNavigate()
  const fileInputRef = useRef()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [verificationStatus, setVerificationStatus] = useState(null)
  const [images, setImages] = useState([])
  const [createdListingId, setCreatedListingId] = useState(null)

  const [form, setForm] = useState({
    // Step 1
    category: 'property',
    purpose: 'rent',
    lister_role: 'owner',
    micheiro_commission_disclosed: false,
    micheiro_commission_description: '',
    // Step 2 — property
    property_type: 'apartment',
    bedrooms: 2, bathrooms: 1, toilets: 0,
    living_rooms: 1, kitchens: 1, dining_rooms: 0,
    offices: 0, storage_rooms: 0, balconies: 0, garages: 0,
    area_m2: '', floor_number: '', total_floors: '',
    furnishing_status: 'unfurnished',
    amenities: [],
    property_condition: 'good',
    available_from: '',
    has_elevator: false, has_security: false, has_generator: false,
    has_water_24h: false, has_internet: false, has_air_conditioning: false,
    has_parking: false, has_garden: false, has_pool: false,
    // Step 2 — vehicle
    vehicle_type: 'car', make: '', model: '', year: '',
    color: '', fuel_type: 'petrol', transmission: 'manual',
    seats: 5, has_ac: false, has_gps: false, driver_included: false,
    min_rental_days: 1,
    // Step 2 — other
    item_type: 'clothing', brand: '', size: '', condition: 'good',
    quantity_available: 1, delivery_available: false,
    // Step 3 — location
    province: 'Luanda', municipality: '', neighbourhood: '',
    street: '', address_complement: '',
    use_gps: false, latitude: '', longitude: '',
    location_privacy: 'neighbourhood',
    // Step 4 — pricing
    title: '', description: '',
    price: '', price_period: 'month', price_negotiable: false,
    deposit_required: false, deposit_amount: '',
    contact_via_chat: true, contact_whatsapp: '',
  })

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))
  const toggle = (key) => setForm(f => ({ ...f, [key]: !f[key] }))
  const toggleAmenity = (v) => setForm(f => ({
    ...f,
    amenities: f.amenities.includes(v) ? f.amenities.filter(a => a !== v) : [...f.amenities, v]
  }))

  useEffect(() => {
    checkVerification()
  }, [])

  const checkVerification = async () => {
    try {
      const res = await client.get('/api/rentals/verify/')
      setVerificationStatus(res.data.status)
    } catch {
      setVerificationStatus('not_submitted')
    }
  }

  const canContinue = () => {
    if (step === 1) return !!form.category
    if (step === 2) {
      if (form.category === 'property') return !!form.property_type
      if (form.category === 'vehicle') return !!form.make && !!form.model
      return true
    }
    if (step === 3) return !!form.province
    if (step === 4) return !!form.title && !!form.price && !!form.description
    if (step === 5) return true
    return true
  }

  const handleCreateListing = async () => {
    setLoading(true)
    try {
      const payload = {
        title: form.title,
        description: form.description,
        category: form.category,
        purpose: form.purpose,
        lister_role: form.lister_role,
        price: form.price,
        price_period: form.price_period,
        price_negotiable: form.price_negotiable,
        deposit_required: form.deposit_required,
        deposit_amount: form.deposit_amount || undefined,
        micheiro_commission_disclosed: form.micheiro_commission_disclosed,
        micheiro_commission_description: form.micheiro_commission_description,
        contact_via_chat: form.contact_via_chat,
        contact_whatsapp: form.contact_whatsapp,
        location: {
          province: form.province,
          municipality: form.municipality,
          neighbourhood: form.neighbourhood,
          street: form.street,
          address_complement: form.address_complement,
          latitude: form.use_gps ? form.latitude : null,
          longitude: form.use_gps ? form.longitude : null,
          has_gps: form.use_gps && !!form.latitude,
          location_privacy: form.location_privacy,
        },
      }

      if (form.category === 'property') {
        payload.property_detail = {
          property_type: form.property_type,
          area_m2: form.area_m2 || null,
          floor_number: form.floor_number || null,
          total_floors: form.total_floors || null,
          bedrooms: form.bedrooms,
          bathrooms: form.bathrooms,
          toilets: form.toilets,
          living_rooms: form.living_rooms,
          kitchens: form.kitchens,
          dining_rooms: form.dining_rooms,
          offices: form.offices,
          storage_rooms: form.storage_rooms,
          balconies: form.balconies,
          garages: form.garages,
          furnishing_status: form.furnishing_status,
          amenities: form.amenities,
          property_condition: form.property_condition,
          available_from: form.available_from || null,
        }
      }

      if (form.category === 'vehicle') {
        payload.vehicle_detail = {
          vehicle_type: form.vehicle_type,
          make: form.make, model: form.model,
          year: form.year || null, color: form.color,
          fuel_type: form.fuel_type, transmission: form.transmission,
          seats: form.seats, has_ac: form.has_ac,
          has_gps: form.has_gps, driver_included: form.driver_included,
          min_rental_days: form.min_rental_days,
        }
      }

      if (form.category === 'other') {
        payload.other_detail = {
          item_type: form.item_type, brand: form.brand,
          size: form.size, condition: form.condition,
          quantity_available: form.quantity_available,
          delivery_available: form.delivery_available,
        }
      }

      const res = await client.post('/api/rentals/create/', payload)
      setCreatedListingId(res.data.id)
      setStep(5) // Go to image upload step
    } catch (err) {
      console.error('Create listing failed:', err.response?.data)
    } finally {
      setLoading(false)
    }
  }

  const handleImageUpload = async (files) => {
    for (const file of Array.from(files)) {
      if (images.length >= 15) break
      const formData = new FormData()
      formData.append('image', file)
      try {
        const res = await client.post(`/api/rentals/${createdListingId}/images/`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        setImages(prev => [...prev, res.data])
      } catch (err) {
        console.error('Image upload failed:', err)
      }
    }
  }

  const handlePublish = async () => {
    setLoading(true)
    try {
      await client.post(`/api/rentals/${createdListingId}/publish/`)
      navigate('/rentals/my', { replace: true })
    } catch (err) {
      console.error('Publish failed:', err)
    } finally {
      setLoading(false)
    }
  }

  // Verification gate
  if (verificationStatus === 'not_submitted' || verificationStatus === 'rejected') {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', padding: 'max(52px, env(safe-area-inset-top)) 0 0' }}>
        <div style={{ padding: '0 20px' }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', marginBottom: 20 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>
            Verificação necessária
          </h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.7, marginBottom: 24 }}>
            Para publicar anúncios de imóveis, veículos ou alugueres, precisamos verificar a sua identidade com o seu BI e uma selfie.
            {verificationStatus === 'rejected' && ' A sua verificação anterior foi rejeitada.'}
          </p>
          <button onClick={() => navigate('/rentals/verify')}
            style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            Fazer verificação de identidade
          </button>
        </div>
      </div>
    )
  }

  if (verificationStatus === 'pending') {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A', padding: 40, gap: 16 }}>
        <div style={{ width: 60, height: 60, borderRadius: '50%', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 28 }}>⏳</span>
        </div>
        <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', textAlign: 'center' }}>Verificação em análise</h2>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center', lineHeight: 1.6 }}>
          A sua identificação está a ser verificada. Será notificado em até 24 horas.
        </p>
        <button onClick={() => navigate(-1)}
          style={{ padding: '10px 24px', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', cursor: 'pointer' }}>
          Voltar
        </button>
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>

      {/* Header */}
      <div style={{ padding: '0 16px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>
            {step < 5 ? 'Criar anúncio' : step === 5 ? 'Adicionar fotos' : 'Rever anúncio'}
          </h1>
        </div>

        {/* Progress */}
        <div style={{ display: 'flex', gap: 4 }}>
          {STEPS.map(s => (
            <div key={s.n} style={{ flex: 1, height: 3, borderRadius: 2, background: s.n <= step ? '#C9A84C' : '#1E1E1E', transition: 'background 0.3s' }} />
          ))}
        </div>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 6 }}>
          Passo {step} de {STEPS.length} — {STEPS[step-1]?.label}
        </p>
      </div>

      {/* Content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 20px' }}>

          {/* STEP 1 — Category, purpose, role */}
          {step === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>O que quer anunciar?</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                  {[{ v: 'property', l: 'Imóvel', icon: '🏠' }, { v: 'vehicle', l: 'Veículo', icon: '🚗' }, { v: 'other', l: 'Outro', icon: '👗' }].map(opt => (
                    <button key={opt.v} onClick={() => set('category', opt.v)}
                      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '16px 10px', borderRadius: 14, border: `1.5px solid ${form.category === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.category === opt.v ? 'rgba(201,168,76,0.1)' : '#141414', cursor: 'pointer' }}>
                      <span style={{ fontSize: 28 }}>{opt.icon}</span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: form.category === opt.v ? 600 : 400, color: form.category === opt.v ? '#C9A84C' : '#FFFFFF' }}>{opt.l}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Para arrendar ou vender?</p>
                <div style={{ display: 'flex', gap: 10 }}>
                  {[{ v: 'rent', l: 'Arrendamento' }, { v: 'sale', l: 'Venda' }, { v: 'both', l: 'Ambos' }].map(opt => (
                    <button key={opt.v} onClick={() => set('purpose', opt.v)}
                      style={{ flex: 1, padding: '12px 0', borderRadius: 12, border: `1.5px solid ${form.purpose === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.purpose === opt.v ? 'rgba(201,168,76,0.1)' : '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: form.purpose === opt.v ? 600 : 400, color: form.purpose === opt.v ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                      {opt.l}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Qual é a sua função?</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[
                    { v: 'owner', l: 'Sou o proprietário', desc: 'Anuncio directamente sem intermediários', color: '#059669' },
                    { v: 'micheiro', l: 'Sou Micheiro (intermediário)', desc: 'Faço a ligação entre proprietário e inquilino', color: '#f59e0b' },
                    { v: 'agent', l: 'Sou agente imobiliário', desc: 'Agente profissional com licença', color: '#6366f1' },
                  ].map(opt => (
                    <button key={opt.v} onClick={() => set('lister_role', opt.v)}
                      style={{ display: 'flex', gap: 12, padding: '14px 16px', borderRadius: 14, border: `1.5px solid ${form.lister_role === opt.v ? opt.color : '#2A2A2A'}`, background: form.lister_role === opt.v ? `${opt.color}10` : '#141414', cursor: 'pointer', textAlign: 'left' }}>
                      <div style={{ width: 22, height: 22, borderRadius: '50%', border: `2px solid ${form.lister_role === opt.v ? opt.color : '#2A2A2A'}`, background: form.lister_role === opt.v ? opt.color : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 1 }}>
                        {form.lister_role === opt.v && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>}
                      </div>
                      <div>
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: form.lister_role === opt.v ? '#FFFFFF' : '#FFFFFF', marginBottom: 2 }}>{opt.l}</p>
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{opt.desc}</p>
                      </div>
                    </button>
                  ))}
                </div>

                {/* Micheiro commission disclosure */}
                {form.lister_role === 'micheiro' && (
                  <div style={{ marginTop: 14, background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: '14px 16px' }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#f59e0b', marginBottom: 10 }}>
                      ⚠️ Como Micheiro, deve divulgar a sua comissão aos utilizadores.
                    </p>
                    <label style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.micheiro_commission_disclosed}
                        onChange={() => toggle('micheiro_commission_disclosed')}
                        style={{ width: 18, height: 18, cursor: 'pointer' }} />
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>
                        Confirmo que cobro comissão e vou informar os utilizadores
                      </span>
                    </label>
                    {form.micheiro_commission_disclosed && (
                      <input type="text" placeholder="ex: 1 mês de renda como comissão"
                        value={form.micheiro_commission_description}
                        onChange={e => set('micheiro_commission_description', e.target.value)}
                        style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', color: '#FFFFFF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 2 — Property details */}
          {step === 2 && form.category === 'property' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Tipo de imóvel</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {PROPERTY_TYPES.map(t => (
                    <button key={t.v} onClick={() => set('property_type', t.v)}
                      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderRadius: 12, border: `1.5px solid ${form.property_type === t.v ? '#C9A84C' : '#2A2A2A'}`, background: form.property_type === t.v ? 'rgba(201,168,76,0.1)' : '#141414', cursor: 'pointer' }}>
                      <span style={{ fontSize: 20 }}>{t.icon}</span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: form.property_type === t.v ? 600 : 400, color: form.property_type === t.v ? '#C9A84C' : '#FFFFFF' }}>{t.l}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Rooms */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Divisões</p>
                <Counter label="🛏 Quartos" value={form.bedrooms} onChange={v => set('bedrooms', v)} />
                <Counter label="🚿 Casas de banho" value={form.bathrooms} onChange={v => set('bathrooms', v)} min={1} />
                <Counter label="🚽 Lavabos" value={form.toilets} onChange={v => set('toilets', v)} />
                <Counter label="🛋 Salas" value={form.living_rooms} onChange={v => set('living_rooms', v)} />
                <Counter label="🍳 Cozinhas" value={form.kitchens} onChange={v => set('kitchens', v)} min={1} />
                <Counter label="🍽 Salas de jantar" value={form.dining_rooms} onChange={v => set('dining_rooms', v)} />
                <Counter label="💼 Escritórios" value={form.offices} onChange={v => set('offices', v)} />
                <Counter label="🏎 Garagens" value={form.garages} onChange={v => set('garages', v)} />
                <Counter label="🌿 Varandas" value={form.balconies} onChange={v => set('balconies', v)} />
              </div>

              {/* Area + floor */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Dimensões</p>
                <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
                  <input type="number" placeholder="Área (m²)" value={form.area_m2}
                    onChange={e => set('area_m2', e.target.value)}
                    style={{ flex: 2, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none' }} />
                  <input type="number" placeholder="Piso nº" value={form.floor_number}
                    onChange={e => set('floor_number', e.target.value)}
                    style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none' }} />
                </div>
              </div>

              {/* Furnishing */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Mobília</p>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[{ v: 'furnished', l: 'Mobilado' }, { v: 'semi', l: 'Semi' }, { v: 'unfurnished', l: 'Sem mobília' }].map(opt => (
                    <button key={opt.v} onClick={() => set('furnishing_status', opt.v)}
                      style={{ flex: 1, padding: '10px 0', borderRadius: 12, border: `1.5px solid ${form.furnishing_status === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.furnishing_status === opt.v ? 'rgba(201,168,76,0.1)' : '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: form.furnishing_status === opt.v ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                      {opt.l}
                    </button>
                  ))}
                </div>
              </div>

              {/* Amenities */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Comodidades</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {AMENITIES.map(a => (
                    <button key={a.v} onClick={() => toggleAmenity(a.v)}
                      style={{ padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${form.amenities.includes(a.v) ? '#C9A84C' : '#2A2A2A'}`, background: form.amenities.includes(a.v) ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: form.amenities.includes(a.v) ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                      {form.amenities.includes(a.v) ? '✓ ' : ''}{a.l}
                    </button>
                  ))}
                </div>
              </div>

              {/* Available from */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Disponível a partir de</p>
                <input type="date" value={form.available_from} onChange={e => set('available_from', e.target.value)}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
              </div>
            </div>
          )}

          {/* STEP 2 — Vehicle details */}
          {step === 2 && form.category === 'vehicle' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Tipo de veículo</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {VEHICLE_TYPES.map(t => (
                    <button key={t.v} onClick={() => set('vehicle_type', t.v)}
                      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderRadius: 12, border: `1.5px solid ${form.vehicle_type === t.v ? '#C9A84C' : '#2A2A2A'}`, background: form.vehicle_type === t.v ? 'rgba(201,168,76,0.1)' : '#141414', cursor: 'pointer' }}>
                      <span style={{ fontSize: 20 }}>{t.icon}</span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: form.vehicle_type === t.v ? '#C9A84C' : '#FFFFFF' }}>{t.l}</span>
                    </button>
                  ))}
                </div>
              </div>
              {[{ key: 'make', label: 'Marca', ph: 'ex: Toyota' }, { key: 'model', label: 'Modelo', ph: 'ex: Land Cruiser' }, { key: 'color', label: 'Cor', ph: 'ex: Branco' }].map(f => (
                <div key={f.key}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>{f.label}</p>
                  <input type="text" placeholder={f.ph} value={form[f.key]} onChange={e => set(f.key, e.target.value)}
                    style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
                </div>
              ))}
              <Counter label="Ano de fabrico" value={form.year || new Date().getFullYear()} onChange={v => set('year', v)} min={1990} max={new Date().getFullYear()} />
              <Counter label="Lugares" value={form.seats} onChange={v => set('seats', v)} min={1} max={60} />
              {[{ key: 'has_ac', l: 'Ar condicionado' }, { key: 'has_gps', l: 'GPS' }, { key: 'driver_included', l: 'Condutor incluído' }].map(opt => (
                <label key={opt.key} style={{ display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', padding: '10px 0', borderBottom: '1px solid #1E1E1E' }}>
                  <input type="checkbox" checked={form[opt.key]} onChange={() => toggle(opt.key)} style={{ width: 18, height: 18 }} />
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }}>{opt.l}</span>
                </label>
              ))}
            </div>
          )}

          {/* STEP 2 — Other */}
          {step === 2 && form.category === 'other' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>Preencha os detalhes do item a alugar.</p>
              {[{ key: 'brand', label: 'Marca (opcional)', ph: 'ex: Nike, Samsung' }, { key: 'size', label: 'Tamanho / Dimensão', ph: 'ex: M, L, 42, 2mx3m' }, { key: 'color', label: 'Cor', ph: 'ex: Azul, Preto' }].map(f => (
                <div key={f.key}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>{f.label}</p>
                  <input type="text" placeholder={f.ph} value={form[f.key] || ''} onChange={e => set(f.key, e.target.value)}
                    style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
                </div>
              ))}
              <Counter label="Quantidade disponível" value={form.quantity_available} onChange={v => set('quantity_available', v)} min={1} max={100} />
            </div>
          )}

          {/* STEP 3 — Location */}
          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Localização</p>

                {/* Province */}
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>Província *</p>
                <select value={form.province} onChange={e => set('province', e.target.value)}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', marginBottom: 12, boxSizing: 'border-box' }}>
                  {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>

                {[
                  { key: 'municipality', label: 'Município', ph: 'ex: Talatona, Belas, Maianga' },
                  { key: 'neighbourhood', label: 'Bairro', ph: 'ex: Futungo de Belas, Miramar' },
                  { key: 'street', label: 'Rua (opcional)', ph: 'ex: Rua das Flores nº 12' },
                  { key: 'address_complement', label: 'Complemento (opcional)', ph: 'ex: Bloco 5, Apt 12B' },
                ].map(f => (
                  <div key={f.key} style={{ marginBottom: 12 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>{f.label}</p>
                    <input type="text" placeholder={f.ph} value={form[f.key]}
                      onChange={e => set(f.key, e.target.value)}
                      style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                ))}
              </div>

              {/* Privacy level */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Precisão da localização mostrada</p>
                {[
                  { v: 'exact', l: 'Localização exacta', desc: 'Mostra rua e número' },
                  { v: 'neighbourhood', l: 'Só o bairro', desc: 'Mostra apenas o bairro (recomendado)' },
                  { v: 'municipality', l: 'Só o município', desc: 'Mais privado — só o município' },
                ].map(opt => (
                  <button key={opt.v} onClick={() => set('location_privacy', opt.v)}
                    style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, border: `1.5px solid ${form.location_privacy === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.location_privacy === opt.v ? 'rgba(201,168,76,0.1)' : '#141414', cursor: 'pointer', textAlign: 'left', marginBottom: 8 }}>
                    <div style={{ width: 18, height: 18, borderRadius: '50%', border: `2px solid ${form.location_privacy === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.location_privacy === opt.v ? '#C9A84C' : 'transparent', flexShrink: 0 }} />
                    <div>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 1 }}>{opt.l}</p>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>{opt.desc}</p>
                    </div>
                  </button>
                ))}
              </div>

              {/* GPS option */}
              <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 14 }}>
                <label style={{ display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', marginBottom: form.use_gps ? 12 : 0 }}>
                  <input type="checkbox" checked={form.use_gps} onChange={() => toggle('use_gps')} style={{ width: 18, height: 18 }} />
                  <div>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 2 }}>Adicionar pin no mapa (GPS)</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>Permite ao utilizador ver a localização exacta no mapa</p>
                  </div>
                </label>
                {form.use_gps && (
                  <div style={{ display: 'flex', gap: 10 }}>
                    <input type="number" step="any" placeholder="Latitude (-8.83...)" value={form.latitude}
                      onChange={e => set('latitude', e.target.value)}
                      style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', color: '#FFFFFF', fontSize: 13, outline: 'none' }} />
                    <input type="number" step="any" placeholder="Longitude (13.23...)" value={form.longitude}
                      onChange={e => set('longitude', e.target.value)}
                      style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', color: '#FFFFFF', fontSize: 13, outline: 'none' }} />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 4 — Title, description, price */}
          {step === 4 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>Título do anúncio *</p>
                <input type="text" placeholder="ex: Apartamento T3 mobilado em Talatona" value={form.title}
                  onChange={e => set('title', e.target.value)} maxLength={200}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
              </div>

              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>Descrição *</p>
                <textarea placeholder="Descreva o imóvel/veículo em detalhes..." value={form.description}
                  onChange={e => set('description', e.target.value)} rows={5}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', resize: 'none', boxSizing: 'border-box' }} />
              </div>

              {/* Price */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>Preço (Kz) *</p>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input type="number" placeholder="0" value={form.price} onChange={e => set('price', e.target.value)}
                    style={{ flex: 2, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none' }} />
                  <select value={form.price_period} onChange={e => set('price_period', e.target.value)}
                    style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 10px', color: '#FFFFFF', fontSize: 12, outline: 'none' }}>
                    <option value="month">/mês</option>
                    <option value="week">/semana</option>
                    <option value="day">/dia</option>
                    <option value="night">/noite</option>
                    <option value="total">total</option>
                    <option value="event">/evento</option>
                  </select>
                </div>
              </div>

              <label style={{ display: 'flex', gap: 10, alignItems: 'center', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.price_negotiable} onChange={() => toggle('price_negotiable')} style={{ width: 18, height: 18 }} />
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }}>Preço negociável</span>
              </label>

              {/* Deposit */}
              <label style={{ display: 'flex', gap: 10, alignItems: 'center', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.deposit_required} onChange={() => toggle('deposit_required')} style={{ width: 18, height: 18 }} />
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }}>Requer caução</span>
              </label>
              {form.deposit_required && (
                <input type="number" placeholder="Valor da caução (Kz)" value={form.deposit_amount}
                  onChange={e => set('deposit_amount', e.target.value)}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
              )}

              {/* WhatsApp */}
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>WhatsApp (opcional)</p>
                <input type="tel" placeholder="+244 9XX XXX XXX" value={form.contact_whatsapp}
                  onChange={e => set('contact_whatsapp', e.target.value)}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
              </div>
            </div>
          )}

          {/* STEP 5 — Images */}
          {step === 5 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6 }}>
                Adicione até <strong style={{ color: '#FFFFFF' }}>15 fotos</strong> do seu imóvel/veículo. A primeira foto será a imagem de capa.
              </p>

              <button onClick={() => fileInputRef.current?.click()}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, height: 140, borderRadius: 16, border: '2px dashed #2A2A2A', background: '#141414', cursor: 'pointer', transition: 'border-color 0.2s' }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                </svg>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>Toque para adicionar fotos</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{images.length}/15 fotos</p>
              </button>

              <input ref={fileInputRef} type="file" accept="image/*" multiple
                onChange={e => handleImageUpload(e.target.files)} style={{ display: 'none' }} />

              {images.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                  {images.map((img, i) => (
                    <div key={img.id} style={{ position: 'relative', aspectRatio: '1', borderRadius: 10, overflow: 'hidden', border: i === 0 ? '2px solid #C9A84C' : '1px solid #2A2A2A' }}>
                      <img src={img.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      {i === 0 && (
                        <div style={{ position: 'absolute', bottom: 4, left: 4, background: '#C9A84C', borderRadius: 6, padding: '1px 6px' }}>
                          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>CAPA</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* STEP 6 — Review */}
          {step === 6 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 14, padding: 16 }}>
                <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#C9A84C', marginBottom: 12 }}>Resumo do anúncio</h3>
                {[
                  { l: 'Título', v: form.title },
                  { l: 'Tipo', v: form.category === 'property' ? 'Imóvel' : form.category === 'vehicle' ? 'Veículo' : 'Outro' },
                  { l: 'Função', v: form.lister_role === 'owner' ? 'Proprietário' : form.lister_role === 'micheiro' ? 'Micheiro' : 'Agente' },
                  { l: 'Preço', v: `${Number(form.price).toLocaleString()} Kz/${form.price_period}` },
                  { l: 'Localização', v: `${form.neighbourhood ? form.neighbourhood + ', ' : ''}${form.municipality ? form.municipality + ', ' : ''}${form.province}` },
                  { l: 'Fotos', v: `${images.length} foto(s)` },
                ].map(r => (
                  <div key={r.l} style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, marginBottom: 8, borderBottom: '1px solid rgba(201,168,76,0.1)' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{r.l}</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500, textAlign: 'right', maxWidth: '60%' }}>{r.v}</span>
                  </div>
                ))}
              </div>

              <div style={{ background: 'rgba(5,150,105,0.06)', border: '1px solid rgba(5,150,105,0.15)', borderRadius: 12, padding: '12px 14px' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#059669' }}>
                  ✓ O anúncio será revisto pela equipa MICHA antes de ser publicado. Tempo médio: 24 horas.
                </p>
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Footer buttons */}
      <div style={{ padding: '14px 16px', paddingBottom: 'max(24px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
        {step < 4 ? (
          <button onClick={() => setStep(s => s + 1)} disabled={!canContinue()}
            style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: canContinue() ? '#C9A84C' : '#2A2A2A', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: canContinue() ? '#0A0A0A' : '#9A9A9A', cursor: canContinue() ? 'pointer' : 'not-allowed' }}>
            Continuar →
          </button>
        ) : step === 4 ? (
          <button onClick={handleCreateListing} disabled={!canContinue() || loading}
            style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: canContinue() && !loading ? '#C9A84C' : '#2A2A2A', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: canContinue() && !loading ? '#0A0A0A' : '#9A9A9A', cursor: canContinue() && !loading ? 'pointer' : 'not-allowed' }}>
            {loading ? 'A guardar...' : 'Guardar e adicionar fotos →'}
          </button>
        ) : step === 5 ? (
          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={() => setStep(6)}
              style={{ flex: 1, padding: '14px 0', borderRadius: 14, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', cursor: 'pointer' }}>
              {images.length === 0 ? 'Saltar' : 'Continuar'}
            </button>
          </div>
        ) : (
          <button onClick={handlePublish} disabled={loading}
            style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1 }}>
            {loading ? 'A submeter...' : '🚀 Submeter para publicação'}
          </button>
        )}
      </div>
    </div>
  )
}
