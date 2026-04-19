import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

const AMENITY_LABELS = {
  water_24h: 'Água 24h', generator: 'Gerador', security: 'Segurança',
  pool: 'Piscina', gym: 'Ginásio', parking: 'Estacionamento',
  garden: 'Jardim', elevator: 'Elevador', internet: 'Internet',
  air_conditioning: 'Ar Condicionado', solar_panels: 'Painéis Solares',
  satellite_tv: 'TV Satélite', intercom: 'Intercomunicador',
  cctv: 'CCTV', pets_allowed: 'Animais Permitidos',
  furnished_kitchen: 'Cozinha Equipada', laundry: 'Lavandaria', storage: 'Arrecadação',
}

function DetailRow({ icon, label, value }) {
  if (!value && value !== 0) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: '1px solid #1E1E1E' }}>
      <span style={{ fontSize: 18, width: 24, textAlign: 'center' }}>{icon}</span>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', flex: 1 }}>{label}</span>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF' }}>{value}</span>
    </div>
  )
}

export default function RentalDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [listing, setListing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState(0)
  const [saved, setSaved] = useState(false)
  const [inquiring, setInquiring] = useState(false)
  const [showInquirySheet, setShowInquirySheet] = useState(false)
  const [inquiryMessage, setInquiryMessage] = useState('')
  const [moveInDate, setMoveInDate] = useState('')
  const [duration, setDuration] = useState('')

  useEffect(() => {
    loadListing()
  }, [id])

  const loadListing = async () => {
    try {
      const res = await client.get(`/api/rentals/${id}/`)
      setListing(res.data)
      setSaved(res.data.is_saved)
    } catch (err) {
      console.error('Listing load failed:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    try {
      if (saved) {
        await client.delete(`/api/rentals/${id}/save/`)
        setSaved(false)
      } else {
        await client.post(`/api/rentals/${id}/save/`)
        setSaved(true)
      }
    } catch {}
  }

  const handleInquire = async () => {
    if (!user) { navigate('/login'); return }
    setInquiring(true)
    try {
      const res = await client.post(`/api/rentals/${id}/inquire/`, {
        message: inquiryMessage || `Olá! Tenho interesse no seu anúncio: ${listing.title}`,
        move_in_date: moveInDate || undefined,
        rental_duration: duration || undefined,
      })

      if (res.data.chat_conversation_id) {
        navigate(`/chat/${res.data.chat_conversation_id}`)
      } else {
        navigate('/chat')
      }
    } catch (err) {
      console.error('Inquiry failed:', err)
    } finally {
      setInquiring(false)
      setShowInquirySheet(false)
    }
  }

  if (loading) return (
    <BuyerLayout hideNav>
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flex: 1 }}>
        <div style={{ width: 28, height: 28, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </div>
      </div>
    </BuyerLayout>
  )

  if (!listing) return null

  const p = listing.property_detail
  const v = listing.vehicle_detail
  const o = listing.other_detail
  const loc = listing.location
  const images = listing.images || []

  const roleConfig = {
    owner: { label: 'Proprietário', color: '#059669', desc: 'Este anúncio é publicado directamente pelo proprietário.' },
    micheiro: { label: 'Micheiro (Intermediário)', color: '#f59e0b', desc: listing.micheiro_commission_description ? `Cobra comissão: ${listing.micheiro_commission_description}` : 'Este anúncio é publicado por um intermediário que cobra comissão.' },
    agent: { label: 'Agente Imobiliário', color: '#6366f1', desc: 'Agente imobiliário profissional.' },
  }[listing.lister_role] || {}

  return (
    <BuyerLayout hideNav>
      {/* Inquiry sheet */}
      {showInquirySheet && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) setShowInquirySheet(false) }}>
          <div style={{ background: '#141414', borderRadius: '20px 20px 0 0', border: '1px solid #1E1E1E', padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A', margin: '0 auto 20px' }} />
            <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 6 }}>Contactar anunciante</h3>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 20 }}>
              Será iniciada uma conversa no chat da MICHA.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 6 }}>Mensagem (opcional)</p>
                <textarea value={inquiryMessage} onChange={e => setInquiryMessage(e.target.value)}
                  placeholder={`Olá! Tenho interesse no seu anúncio: ${listing.title}`}
                  rows={3}
                  style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 13, outline: 'none', resize: 'none', boxSizing: 'border-box' }} />
              </div>

              {listing.category === 'property' && (
                <>
                  <div>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 6 }}>Data de entrada pretendida</p>
                    <input type="date" value={moveInDate} onChange={e => setMoveInDate(e.target.value)}
                      style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                  <div>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 6 }}>Duração pretendida</p>
                    <input type="text" value={duration} onChange={e => setDuration(e.target.value)}
                      placeholder="ex: 6 meses, 1 ano"
                      style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                </>
              )}

              <button onClick={handleInquire} disabled={inquiring}
                style={{ padding: '14px 0', borderRadius: 14, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: inquiring ? 'not-allowed' : 'pointer', opacity: inquiring ? 0.6 : 1 }}>
                {inquiring ? 'A abrir chat...' : '💬 Iniciar conversa'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="screen" style={{ flex: 1 }}>
        {/* Image gallery */}
        <div style={{ position: 'relative' }}>
          <div style={{ height: 300, background: '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {images[selectedImage]?.image_url
              ? <img src={images[selectedImage].image_url} alt={listing.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
            }
            {/* Back button */}
            <button onClick={() => navigate(-1)} style={{ position: 'absolute', top: 16, left: 16, width: 36, height: 36, borderRadius: '50%', background: 'rgba(0,0,0,0.6)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
            </button>
            {/* Image count */}
            {images.length > 1 && (
              <div style={{ position: 'absolute', bottom: 12, right: 12, background: 'rgba(0,0,0,0.6)', borderRadius: 20, padding: '3px 10px' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#FFFFFF' }}>{selectedImage + 1}/{images.length}</span>
              </div>
            )}
            {/* Save button */}
            <button onClick={handleSave} style={{ position: 'absolute', top: 16, right: 16, width: 36, height: 36, borderRadius: '50%', background: 'rgba(0,0,0,0.6)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill={saved ? '#C9A84C' : 'none'} stroke={saved ? '#C9A84C' : '#FFFFFF'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </button>
          </div>

          {/* Thumbnails */}
          {images.length > 1 && (
            <div style={{ display: 'flex', gap: 6, padding: '8px 16px', overflowX: 'auto', scrollbarWidth: 'none' }}>
              {images.map((img, i) => (
                <button key={i} onClick={() => setSelectedImage(i)}
                  style={{ width: 52, height: 52, borderRadius: 8, flexShrink: 0, border: `2px solid ${selectedImage === i ? '#C9A84C' : 'transparent'}`, background: '#1E1E1E', overflow: 'hidden', cursor: 'pointer', padding: 0 }}>
                  {img.image_url && <img src={img.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Content */}
        <div style={{ padding: '16px 16px 0' }}>
          {/* Title + price */}
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', marginBottom: 8, lineHeight: 1.3 }}>{listing.title}</h1>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 24, fontWeight: 700, color: '#C9A84C' }}>
              {listing.formatted_price || `${Number(listing.price).toLocaleString()} Kz`}
            </span>
            {listing.price_negotiable && (
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', fontStyle: 'italic' }}>Negociável</span>
            )}
          </div>

          {/* Location */}
          {loc && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
              </svg>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>
                {loc.neighbourhood && `${loc.neighbourhood}, `}{loc.municipality && `${loc.municipality}, `}{loc.province}
              </span>
              {loc.has_gps && (
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', padding: '1px 6px', borderRadius: 20 }}>Ver no mapa</span>
              )}
            </div>
          )}

          {/* Lister role disclosure */}
          <div style={{ background: `${roleConfig.color}10`, border: `1px solid ${roleConfig.color}30`, borderRadius: 12, padding: '10px 14px', marginBottom: 16 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: roleConfig.color, marginBottom: 3 }}>
              {listing.lister_verified ? '✓ ' : ''}{roleConfig.label}
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{roleConfig.desc}</p>
          </div>

          {/* Property details */}
          {p && (
            <div style={{ marginBottom: 20 }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>Detalhes do imóvel</h2>

              {/* Key stats */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
                {[
                  { icon: '🛏', label: 'Quartos', value: p.bedrooms },
                  { icon: '🚿', label: 'WC', value: p.bathrooms },
                  { icon: '📐', label: 'Área', value: p.area_m2 ? `${p.area_m2}m²` : null },
                  { icon: '🚗', label: 'Garagens', value: p.garages || null },
                ].filter(s => s.value).map(stat => (
                  <div key={stat.label} style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: '12px 8px', textAlign: 'center' }}>
                    <p style={{ fontSize: 20, marginBottom: 4 }}>{stat.icon}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF', marginBottom: 2 }}>{stat.value}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>{stat.label}</p>
                  </div>
                ))}
              </div>

              <DetailRow icon="🏠" label="Tipo" value={p.property_type} />
              <DetailRow icon="🛋" label="Mobília" value={p.furnishing_status === 'furnished' ? 'Mobilado' : p.furnishing_status === 'semi' ? 'Semi-mobilado' : 'Sem mobília'} />
              <DetailRow icon="🍳" label="Cozinhas" value={p.kitchens} />
              <DetailRow icon="🪑" label="Salas" value={p.living_rooms} />
              <DetailRow icon="🏗" label="Estado" value={p.property_condition} />
              {p.available_from && <DetailRow icon="📅" label="Disponível a partir de" value={new Date(p.available_from).toLocaleDateString('pt-AO')} />}

              {/* Amenities */}
              {p.amenities?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 10 }}>Comodidades</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {p.amenities.map(a => (
                      <span key={a} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669', background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', padding: '4px 10px', borderRadius: 20 }}>
                        ✓ {AMENITY_LABELS[a] || a}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Vehicle details */}
          {v && (
            <div style={{ marginBottom: 20 }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>Detalhes do veículo</h2>
              <DetailRow icon="🚗" label="Marca / Modelo" value={`${v.make} ${v.model}`} />
              <DetailRow icon="📅" label="Ano" value={v.year} />
              <DetailRow icon="⛽" label="Combustível" value={v.fuel_type} />
              <DetailRow icon="⚙️" label="Transmissão" value={v.transmission} />
              <DetailRow icon="👥" label="Lugares" value={v.seats} />
              <DetailRow icon="📍" label="Matrícula" value={v.plate_number || null} />
              {v.driver_included && <DetailRow icon="👨" label="Condutor incluído" value="Sim" />}
              {v.insurance_included && <DetailRow icon="🛡" label="Seguro incluído" value="Sim" />}
            </div>
          )}

          {/* Description */}
          <div style={{ marginBottom: 20 }}>
            <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#FFFFFF', marginBottom: 10 }}>Descrição</h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.7 }}>{listing.description}</p>
          </div>

          {/* Deposit */}
          {listing.deposit_required && listing.deposit_amount && (
            <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: '12px 14px', marginBottom: 20 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#f59e0b' }}>
                ⚠️ Caução: {Number(listing.deposit_amount).toLocaleString()} Kz
              </p>
            </div>
          )}

          <div style={{ height: 100 }} />
        </div>
      </div>

      {/* Sticky CTA */}
      <div style={{ padding: '12px 16px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', background: '#0A0A0A', borderTop: '1px solid #1E1E1E', flexShrink: 0, display: 'flex', gap: 10 }}>
        <button onClick={handleSave}
          style={{ width: 48, height: 48, borderRadius: 14, border: `1.5px solid ${saved ? '#C9A84C' : '#2A2A2A'}`, background: saved ? 'rgba(201,168,76,0.1)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill={saved ? '#C9A84C' : 'none'} stroke={saved ? '#C9A84C' : '#9A9A9A'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
          </svg>
        </button>
        <button onClick={() => setShowInquirySheet(true)}
          style={{ flex: 1, padding: '14px 0', borderRadius: 14, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          💬 Contactar via chat
        </button>
      </div>
    </BuyerLayout>
  )
}
