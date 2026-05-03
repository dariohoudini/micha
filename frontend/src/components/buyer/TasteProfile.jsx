import { useState, useEffect } from 'react'
import client from '@/api/client'

const GOLD = '#C9A84C'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

export default function TasteProfile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/api/v1/ai/taste-profile/')
      .then(r => setProfile(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading || !profile) return null

  const interests = profile.top_categories || profile.interests || []
  const brands = profile.top_brands || []
  const priceRange = profile.price_range || {}

  return (
    <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 14, margin: '0 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: TEXT, margin: 0 }}>
          O teu perfil de gostos
        </p>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: GOLD, background: 'rgba(201,168,76,0.1)', padding: '2px 8px', borderRadius: 4 }}>
          IA MICHA
        </span>
      </div>

      {interests.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Categorias favoritas</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {interests.slice(0, 6).map((cat, i) => (
              <span key={i} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD, background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)', padding: '3px 8px', borderRadius: 20 }}>
                {cat.name || cat}
              </span>
            ))}
          </div>
        </div>
      )}

      {brands.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Marcas preferidas</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {brands.slice(0, 4).map((brand, i) => (
              <span key={i} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: TEXT, background: '#2A2A2A', padding: '3px 8px', borderRadius: 20 }}>
                {brand.name || brand}
              </span>
            ))}
          </div>
        </div>
      )}

      {priceRange.min !== undefined && (
        <div>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Orçamento habitual</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, margin: 0 }}>
            {Number(priceRange.min).toLocaleString()} – {Number(priceRange.max).toLocaleString()} Kz
          </p>
        </div>
      )}

      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '10px 0 0', lineHeight: 1.5 }}>
        Baseado no teu histórico de compras e navegação. Actualiza automaticamente.
      </p>
    </div>
  )
}
