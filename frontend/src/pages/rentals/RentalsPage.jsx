import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const CATEGORIES = [
  { id: 'all', label: 'Todos', icon: '🏠' },
  { id: 'property', label: 'Imóveis', icon: '🏢' },
  { id: 'vehicle', label: 'Veículos', icon: '🚗' },
  { id: 'other', label: 'Outros', icon: '📦' },
]

const PURPOSES = [
  { id: 'all', label: 'Todos' },
  { id: 'rent', label: 'Arrendar' },
  { id: 'sale', label: 'Comprar' },
]

const PROVINCES = [
  'Todas', 'Luanda', 'Benguela', 'Huambo', 'Huíla', 'Cabinda',
  'Namibe', 'Malanje', 'Uíge',
]

function ListingCard({ listing, onPress }) {
  const isMicheiro = listing.lister_role === 'micheiro'

  return (
    <button onClick={() => onPress(listing)}
      style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column', width: '100%' }}>

      {/* Cover image */}
      <div style={{ height: 180, background: '#1E1E1E', position: 'relative', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {listing.cover_image
          ? <img src={listing.cover_image} alt={listing.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <span style={{ fontSize: 40 }}>{listing.category === 'property' ? '🏠' : listing.category === 'vehicle' ? '🚗' : '📦'}</span>
        }
        {/* Purpose badge */}
        <div style={{ position: 'absolute', top: 10, left: 10, background: listing.purpose === 'sale' ? '#3b82f6' : '#C9A84C', borderRadius: 8, padding: '3px 10px' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: '#0A0A0A' }}>
            {listing.purpose === 'sale' ? 'Venda' : listing.purpose === 'rent_sale' ? 'Arrend./Venda' : 'Arrendamento'}
          </span>
        </div>
        {/* Micheiro badge */}
        {isMicheiro && (
          <div style={{ position: 'absolute', top: 10, right: 10, background: 'rgba(0,0,0,0.7)', borderRadius: 8, padding: '3px 10px' }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>Micheiro</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ padding: '12px 14px 14px' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {listing.title}
        </p>

        {/* Location */}
        {listing.display_location && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 8 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
            </svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{listing.display_location}</span>
          </div>
        )}

        {/* Property details */}
        {listing.bedroom_label && (
          <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>🛏 {listing.bedroom_label}</span>
          </div>
        )}

        {/* Price */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>
            {Number(listing.price).toLocaleString()} Kz
          </span>
          {listing.price_period === 'month' && (
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>/mês</span>
          )}
          {listing.price_negotiable && (
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#059669' }}>Negociável</span>
          )}
        </div>

        {/* Micheiro commission */}
        {isMicheiro && listing.micheiro_commission_pct && (
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#f59e0b', marginTop: 4 }}>
            ℹ️ Comissão do micheiro: {listing.micheiro_commission_pct}%
          </p>
        )}
      </div>
    </button>
  )
}

export default function RentalsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [listings, setListings] = useState([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('all')
  const [purpose, setPurpose] = useState('all')
  const [province, setProvince] = useState('Todas')
  const [priceMax, setPriceMax] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [showFilters, setShowFilters] = useState(false)

  const loadListings = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, limit: 20 }
      if (category !== 'all') params.category = category
      if (purpose !== 'all') params.purpose = purpose
      if (province !== 'Todas') params.province = province
      if (priceMax) params.price_max = priceMax

      const res = await client.get('/api/v1/rentals/', { params })
      setListings(res.data.results || res.data || [])
      setTotal(res.data.count || 0)
    } catch {
      setListings([])
    } finally {
      setLoading(false)
    }
  }, [category, purpose, province, priceMax, page])

  useEffect(() => { loadListings() }, [loadListings])

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <BuyerLayout>
      {/* Header */}
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Anúncios</h1>
            <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{total} anúncios disponíveis</p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setShowFilters(v => !v)}
              style={{ height: 40, padding: '0 14px', borderRadius: 12, border: `1px solid ${showFilters ? '#C9A84C' : '#2A2A2A'}`, background: showFilters ? 'rgba(201,168,76,0.1)' : '#1E1E1E', ...S, fontSize: 12, color: showFilters ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
              ⚙ Filtros
            </button>
            <button onClick={() => navigate('/rentals/new')}
              style={{ height: 40, padding: '0 14px', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
              + Anunciar
            </button>
          </div>
        </div>

        {/* Category tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {CATEGORIES.map(cat => (
            <button key={cat.id} onClick={() => { setCategory(cat.id); setPage(1) }}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${category === cat.id ? '#C9A84C' : '#2A2A2A'}`, background: category === cat.id ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: category === cat.id ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', flexShrink: 0 }}>
              <span>{cat.icon}</span> {cat.label}
            </button>
          ))}
        </div>

        {/* Filters panel */}
        {showFilters && (
          <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16, marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Purpose */}
            <div>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Finalidade</p>
              <div style={{ display: 'flex', gap: 8 }}>
                {PURPOSES.map(p => (
                  <button key={p.id} onClick={() => setPurpose(p.id)}
                    style={{ padding: '6px 14px', borderRadius: 50, border: `1px solid ${purpose === p.id ? '#C9A84C' : '#2A2A2A'}`, background: purpose === p.id ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: purpose === p.id ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Province */}
            <div>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Província</p>
              <select value={province} onChange={e => setProvince(e.target.value)}
                style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', ...S, fontSize: 13, color: '#FFFFFF', outline: 'none' }}>
                {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {/* Price max */}
            <div>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Preço máximo (Kz)</p>
              <input type="number" value={priceMax} onChange={e => setPriceMax(e.target.value)}
                placeholder="Ex: 150000"
                style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', ...S, fontSize: 13, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }} />
            </div>
          </div>
        )}
      </div>

      {/* Listings grid */}
      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          </div>
        ) : listings.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 16, padding: '0 32px' }}>
            <span style={{ fontSize: 48 }}>🔍</span>
            <p style={{ ...S, fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>Sem anúncios encontrados com estes filtros.</p>
            <button onClick={() => { setCategory('all'); setPurpose('all'); setProvince('Todas'); setPriceMax('') }}
              style={{ padding: '10px 24px', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 13, color: '#FFFFFF', cursor: 'pointer' }}>
              Limpar filtros
            </button>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {listings.map(listing => (
              <ListingCard key={listing.id} listing={listing}
                onPress={l => navigate(`/rentals/${l.id}`)} />
            ))}
          </div>
        )}
      </div>
    </BuyerLayout>
  )
}
