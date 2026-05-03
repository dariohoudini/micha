import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

const STEPS = [
  { id: 1, label: 'Tipo & Função' },
  { id: 2, label: 'Detalhes' },
  { id: 3, label: 'Localização' },
  { id: 4, label: 'Fotos & Preço' },
]

const ANGOLA_PROVINCES = [
  'Luanda','Benguela','Huambo','Huíla','Cabinda','Uíge','Namibe',
  'Malanje','Bié','Moxico','Cunene','Cuando Cubango','Lunda Norte',
  'Lunda Sul','Kwanza Norte','Kwanza Sul','Bengo','Zaire',
]

const inputStyle = {
  width: '100%', background: '#141414', border: '1px solid #2A2A2A',
  borderRadius: 12, padding: '13px 16px', fontFamily: "'DM Sans', sans-serif",
  fontSize: 14, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box',
}

const labelStyle = {
  fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600,
  color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em',
  marginBottom: 6, display: 'block',
}

function ToggleChip({ label, value, onChange }) {
  return (
    <button type="button" onClick={() => onChange(!value)}
      style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${value ? '#C9A84C' : '#2A2A2A'}`, background: value ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: value ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', flexShrink: 0 }}>
      {value && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>}
      {label}
    </button>
  )
}

export default function CreateListingPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const fileInputRef = useRef()

  const [form, setForm] = useState({
    // Step 1
    category: 'property',
    purpose: 'rent',
    lister_role: 'owner',
    micheiro_commission_pct: '',
    // Step 2 — common
    title: '',
    description: '',
    // Property
    property_type: 'apartment',
    bedrooms: '2',
    bathrooms: '1',
    living_rooms: '1',
    kitchens: '1',
    total_area_m2: '',
    floor_number: '',
    furnishing: 'unfurnished',
    // Amenities
    has_parking: false, has_generator: false, has_water_tank: false,
    has_security: false, has_elevator: false, has_balcony: false,
    has_air_conditioning: false, has_internet: false,
    is_gated_community: false, pets_allowed: false,
    has_swimming_pool: false, has_gym: false,
    // Utilities
    water_included: false, electricity_included: false, internet_included: false,
    deposit_months: '1',
    // Vehicle
    vehicle_type: 'car',
    make: '', model: '', year: '', color: '',
    fuel_type: 'petrol', transmission: 'manual', seats: '5', mileage_km: '',
    with_driver: false,
    // Step 3 — location
    province: 'Luanda', municipality: '', neighbourhood: '',
    street: '', landmark: '', latitude: '', longitude: '',
    location_source: 'manual', privacy_level: 'approximate',
    // Step 4
    price: '', price_period: 'month', price_negotiable: false,
    available_from: '',
  })
  const [photos, setPhotos] = useState([])

  const update = (field, value) => setForm(prev => ({ ...prev, [field]: value }))

  const canContinue = () => {
    if (step === 1) return !!form.category && !!form.purpose && !!form.lister_role
    if (step === 2) return form.title.trim().length >= 5 && form.description.trim().length >= 20
    if (step === 3) return !!form.province
    if (step === 4) return !!form.price && photos.length >= 1
    return false
  }

  const handleSubmit = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = new FormData()

      // Core fields
      const fields = ['category','purpose','lister_role','title','description',
        'price','price_period','price_negotiable','available_from']
      fields.forEach(f => form[f] !== '' && data.append(f, form[f]))

      if (form.lister_role === 'micheiro' && form.micheiro_commission_pct) {
        data.append('micheiro_commission_pct', form.micheiro_commission_pct)
      }

      // Location
      const locFields = ['province','municipality','neighbourhood','street',
        'landmark','latitude','longitude','location_source','privacy_level']
      const locationData = {}
      locFields.forEach(f => { if (form[f]) locationData[f] = form[f] })
      data.append('location', JSON.stringify(locationData))

      // Category-specific details
      if (form.category === 'property') {
        const propFields = ['property_type','bedrooms','bathrooms','living_rooms',
          'kitchens','total_area_m2','floor_number','furnishing','deposit_months',
          'has_parking','has_generator','has_water_tank','has_security','has_elevator',
          'has_balcony','has_air_conditioning','has_internet','is_gated_community',
          'pets_allowed','has_swimming_pool','has_gym',
          'water_included','electricity_included','internet_included']
        const propData = {}
        propFields.forEach(f => { if (form[f] !== '') propData[f] = form[f] })
        data.append('property_detail', JSON.stringify(propData))
      } else if (form.category === 'vehicle') {
        const vehData = {
          vehicle_type: form.vehicle_type, make: form.make, model: form.model,
          year: form.year, color: form.color, fuel_type: form.fuel_type,
          transmission: form.transmission, seats: form.seats,
          mileage_km: form.mileage_km, with_driver: form.with_driver,
        }
        data.append('vehicle_detail', JSON.stringify(vehData))
      }

      // Photos
      photos.forEach(photo => data.append('images', photo))

      await client.post('/api/v1/rentals/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      navigate('/rentals/my', { replace: true })
    } catch (err) {
      setError(err.response?.data?.error || 'Erro ao criar anúncio. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>

      {/* Header */}
      <div style={{ padding: '0 20px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : navigate(-1)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Novo Anúncio</h1>
        </div>

        {/* Progress */}
        <div style={{ display: 'flex', gap: 4 }}>
          {STEPS.map(s => (
            <div key={s.id} style={{ flex: 1 }}>
              <div style={{ height: 3, borderRadius: 2, background: step >= s.id ? '#C9A84C' : '#1E1E1E', transition: 'background 0.3s', marginBottom: 4 }} />
              <span style={{ ...S, fontSize: 9, color: step >= s.id ? '#C9A84C' : '#9A9A9A' }}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '8px 20px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Step 1 — Type & Role */}
          {step === 1 && <>
            <div>
              <label style={labelStyle}>Tipo de anúncio</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {[{v:'property',l:'🏠 Imóvel'},{v:'vehicle',l:'🚗 Veículo'},{v:'other',l:'📦 Outro'}].map(opt => (
                  <button key={opt.v} onClick={() => update('category', opt.v)} type="button"
                    style={{ flex: 1, padding: '12px 8px', borderRadius: 12, border: `1.5px solid ${form.category === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.category === opt.v ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: form.category === opt.v ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                    {opt.l}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label style={labelStyle}>Finalidade</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {[{v:'rent',l:'Arrendar'},{v:'sale',l:'Vender'},{v:'rent_sale',l:'Ambos'}].map(opt => (
                  <button key={opt.v} onClick={() => update('purpose', opt.v)} type="button"
                    style={{ flex: 1, padding: '12px 8px', borderRadius: 12, border: `1.5px solid ${form.purpose === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: form.purpose === opt.v ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: form.purpose === opt.v ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                    {opt.l}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label style={labelStyle}>O seu papel</label>
              {[{v:'owner',l:'Proprietário',d:'Sou dono do imóvel/veículo'},{v:'micheiro',l:'Micheiro',d:'Sou intermediário — ganho comissão'},{v:'agent',l:'Agente',d:'Trabalho numa imobiliária'}].map(opt => (
                <button key={opt.v} onClick={() => update('lister_role', opt.v)} type="button"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', padding: '14px 16px', borderRadius: 12, border: `1.5px solid ${form.lister_role === opt.v ? '#C9A84C' : '#1E1E1E'}`, background: form.lister_role === opt.v ? 'rgba(201,168,76,0.08)' : '#141414', cursor: 'pointer', marginBottom: 8, textAlign: 'left' }}>
                  <div>
                    <p style={{ ...S, fontSize: 14, fontWeight: 500, color: '#FFFFFF', marginBottom: 2 }}>{opt.l}</p>
                    <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{opt.d}</p>
                  </div>
                  {form.lister_role === opt.v && (
                    <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                    </div>
                  )}
                </button>
              ))}
            </div>

            {form.lister_role === 'micheiro' && (
              <div>
                <label style={labelStyle}>Comissão (%)</label>
                <input type="number" value={form.micheiro_commission_pct}
                  onChange={e => update('micheiro_commission_pct', e.target.value)}
                  placeholder="Ex: 5" min="0" max="30" style={inputStyle} />
                <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>
                  Esta comissão será mostrada transparentemente no anúncio.
                </p>
              </div>
            )}
          </>}

          {/* Step 2 — Details */}
          {step === 2 && <>
            <div>
              <label style={labelStyle}>Título do anúncio</label>
              <input value={form.title} onChange={e => update('title', e.target.value)}
                placeholder="Ex: Apartamento T3 mobilado em Talatona"
                style={inputStyle} />
            </div>

            <div>
              <label style={labelStyle}>Descrição</label>
              <textarea value={form.description} onChange={e => update('description', e.target.value)}
                placeholder="Descreva o imóvel/veículo em detalhe..."
                rows={4}
                style={{ ...inputStyle, resize: 'vertical', minHeight: 100 }} />
            </div>

            {form.category === 'property' && <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {[{f:'bedrooms',l:'Quartos'},{f:'bathrooms',l:'Casas de banho'},{f:'living_rooms',l:'Salas'},{f:'kitchens',l:'Cozinhas'}].map(item => (
                  <div key={item.f}>
                    <label style={labelStyle}>{item.l}</label>
                    <input type="number" value={form[item.f]} onChange={e => update(item.f, e.target.value)}
                      min="0" max="20" style={inputStyle} />
                  </div>
                ))}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Área total (m²)</label>
                  <input type="number" value={form.total_area_m2} onChange={e => update('total_area_m2', e.target.value)}
                    placeholder="Ex: 120" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Piso nº</label>
                  <input type="number" value={form.floor_number} onChange={e => update('floor_number', e.target.value)}
                    placeholder="Ex: 3" style={inputStyle} />
                </div>
              </div>

              <div>
                <label style={labelStyle}>Mobilado</label>
                <select value={form.furnishing} onChange={e => update('furnishing', e.target.value)} style={inputStyle}>
                  <option value="furnished">Mobilado</option>
                  <option value="semi">Semi-mobilado</option>
                  <option value="unfurnished">Sem mobília</option>
                </select>
              </div>

              <div>
                <label style={labelStyle}>Comodidades</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {[
                    {f:'has_parking',l:'Estacionamento'},{f:'has_generator',l:'Gerador'},
                    {f:'has_water_tank',l:'Depósito água'},{f:'has_security',l:'Segurança 24h'},
                    {f:'has_elevator',l:'Elevador'},{f:'has_balcony',l:'Varanda'},
                    {f:'has_air_conditioning',l:'Ar cond.'},{f:'has_internet',l:'Internet'},
                    {f:'is_gated_community',l:'Condomínio'},{f:'pets_allowed',l:'Animais'},
                    {f:'has_swimming_pool',l:'Piscina'},{f:'has_gym',l:'Ginásio'},
                  ].map(item => (
                    <ToggleChip key={item.f} label={item.l} value={form[item.f]} onChange={v => update(item.f, v)} />
                  ))}
                </div>
              </div>

              <div>
                <label style={labelStyle}>Incluído na renda</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[{f:'water_included',l:'Água'},{f:'electricity_included',l:'Luz'},{f:'internet_included',l:'Internet'}].map(item => (
                    <ToggleChip key={item.f} label={item.l} value={form[item.f]} onChange={v => update(item.f, v)} />
                  ))}
                </div>
              </div>

              <div>
                <label style={labelStyle}>Meses de caução</label>
                <input type="number" value={form.deposit_months} onChange={e => update('deposit_months', e.target.value)}
                  min="0" max="12" style={inputStyle} />
              </div>
            </>}

            {form.category === 'vehicle' && <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {[{f:'make',l:'Marca',p:'Ex: Toyota'},{f:'model',l:'Modelo',p:'Ex: Hilux'},{f:'year',l:'Ano',p:'Ex: 2020'},{f:'color',l:'Cor',p:'Ex: Branco'}].map(item => (
                  <div key={item.f}>
                    <label style={labelStyle}>{item.l}</label>
                    <input value={form[item.f]} onChange={e => update(item.f, e.target.value)}
                      placeholder={item.p} style={inputStyle} />
                  </div>
                ))}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Combustível</label>
                  <select value={form.fuel_type} onChange={e => update('fuel_type', e.target.value)} style={inputStyle}>
                    <option value="petrol">Gasolina</option>
                    <option value="diesel">Gasóleo</option>
                    <option value="electric">Eléctrico</option>
                    <option value="hybrid">Híbrido</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Transmissão</label>
                  <select value={form.transmission} onChange={e => update('transmission', e.target.value)} style={inputStyle}>
                    <option value="manual">Manual</option>
                    <option value="automatic">Automático</option>
                  </select>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <ToggleChip label="Com condutor" value={form.with_driver} onChange={v => update('with_driver', v)} />
              </div>
            </>}
          </>}

          {/* Step 3 — Location */}
          {step === 3 && <>
            <div>
              <label style={labelStyle}>Método de localização</label>
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <button onClick={() => update('location_source', 'manual')} type="button"
                  style={{ flex: 1, padding: '12px', borderRadius: 12, border: `1.5px solid ${form.location_source === 'manual' ? '#C9A84C' : '#2A2A2A'}`, background: form.location_source === 'manual' ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 13, color: form.location_source === 'manual' ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                  ✏️ Endereço manual
                </button>
                <button onClick={() => update('location_source', 'gps')} type="button"
                  style={{ flex: 1, padding: '12px', borderRadius: 12, border: `1.5px solid ${form.location_source === 'gps' ? '#C9A84C' : '#2A2A2A'}`, background: form.location_source === 'gps' ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 13, color: form.location_source === 'gps' ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                  📍 GPS / Google Maps
                </button>
              </div>
            </div>

            <div>
              <label style={labelStyle}>Província</label>
              <select value={form.province} onChange={e => update('province', e.target.value)} style={inputStyle}>
                {ANGOLA_PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {[{f:'municipality',l:'Município',p:'Ex: Belas'},{f:'neighbourhood',l:'Bairro',p:'Ex: Talatona'},{f:'street',l:'Rua / Avenida',p:'Ex: Rua das Acácias'},{f:'landmark',l:'Ponto de referência',p:"Ex: Perto do Shoprite"}].map(item => (
              <div key={item.f}>
                <label style={labelStyle}>{item.l}</label>
                <input value={form[item.f]} onChange={e => update(item.f, e.target.value)}
                  placeholder={item.p} style={inputStyle} />
              </div>
            ))}

            {form.location_source === 'gps' && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {[{f:'latitude',l:'Latitude',p:'-8.838'},{f:'longitude',l:'Longitude',p:'13.234'}].map(item => (
                  <div key={item.f}>
                    <label style={labelStyle}>{item.l}</label>
                    <input type="number" step="any" value={form[item.f]} onChange={e => update(item.f, e.target.value)}
                      placeholder={item.p} style={inputStyle} />
                  </div>
                ))}
              </div>
            )}

            <div>
              <label style={labelStyle}>Privacidade da localização</label>
              <select value={form.privacy_level} onChange={e => update('privacy_level', e.target.value)} style={inputStyle}>
                <option value="approximate">Mostrar bairro (recomendado)</option>
                <option value="city">Mostrar apenas município</option>
                <option value="exact">Mostrar endereço exacto</option>
              </select>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>
                O endereço exacto é revelado apenas após o comprador enviar uma mensagem.
              </p>
            </div>
          </>}

          {/* Step 4 — Photos & Price */}
          {step === 4 && <>
            <div>
              <label style={labelStyle}>Fotos ({photos.length}/15)</label>
              <input ref={fileInputRef} type="file" accept="image/*" multiple style={{ display: 'none' }}
                onChange={e => {
                  const newFiles = Array.from(e.target.files)
                  setPhotos(prev => [...prev, ...newFiles].slice(0, 15))
                }} />

              <button type="button" onClick={() => fileInputRef.current?.click()}
                style={{ width: '100%', height: 100, borderRadius: 14, border: '2px dashed #2A2A2A', background: '#141414', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 24 }}>📷</span>
                <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>
                  {photos.length === 0 ? 'Adicionar fotos (mínimo 1, máximo 15)' : `Adicionar mais fotos (${15 - photos.length} restantes)`}
                </span>
              </button>

              {photos.length > 0 && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {photos.map((photo, i) => (
                    <div key={i} style={{ position: 'relative', width: 70, height: 70 }}>
                      <img src={URL.createObjectURL(photo)} alt=""
                        style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 10, border: i === 0 ? '2px solid #C9A84C' : '1px solid #2A2A2A' }} />
                      {i === 0 && (
                        <div style={{ position: 'absolute', bottom: 2, left: 2, background: '#C9A84C', borderRadius: 4, padding: '1px 4px' }}>
                          <span style={{ ...S, fontSize: 8, color: '#0A0A0A', fontWeight: 700 }}>CAPA</span>
                        </div>
                      )}
                      <button onClick={() => setPhotos(prev => prev.filter((_, idx) => idx !== i))}
                        style={{ position: 'absolute', top: -4, right: -4, width: 18, height: 18, borderRadius: '50%', background: '#dc2626', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#FFFFFF', fontSize: 10 }}>
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>Preço (Kz)</label>
                <input type="number" value={form.price} onChange={e => update('price', e.target.value)}
                  placeholder="Ex: 150000" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Período</label>
                <select value={form.price_period} onChange={e => update('price_period', e.target.value)} style={inputStyle}>
                  <option value="month">Por mês</option>
                  <option value="day">Por dia</option>
                  <option value="week">Por semana</option>
                  <option value="total">Preço total</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <ToggleChip label="Preço negociável" value={form.price_negotiable} onChange={v => update('price_negotiable', v)} />
            </div>

            <div>
              <label style={labelStyle}>Disponível a partir de</label>
              <input type="date" value={form.available_from} onChange={e => update('available_from', e.target.value)}
                style={inputStyle} />
            </div>

            {error && (
              <div style={{ background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 10, padding: 12 }}>
                <p style={{ ...S, fontSize: 13, color: '#ef4444' }}>{error}</p>
              </div>
            )}
          </>}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: '14px 20px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0, display: 'flex', gap: 10 }}>
        {step < 4 ? (
          <button onClick={() => setStep(s => s + 1)} className="btn-primary"
            disabled={!canContinue()} style={{ flex: 1, opacity: canContinue() ? 1 : 0.4 }}>
            Continuar
          </button>
        ) : (
          <button onClick={handleSubmit} className="btn-primary"
            disabled={!canContinue() || loading} style={{ flex: 1, opacity: canContinue() && !loading ? 1 : 0.4 }}>
            {loading ? 'A publicar...' : '🚀 Publicar anúncio'}
          </button>
        )}
      </div>
    </div>
  )
}
