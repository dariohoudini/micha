import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const CATEGORY_TABS = [
  { v: '', l: 'Todos', icon: '🏠' },
  { v: 'property', l: 'Imóveis', icon: '🏢' },
  { v: 'vehicle', l: 'Veículos', icon: '🚗' },
  { v: 'other', l: 'Outros', icon: '👗' },
]

const PURPOSE_FILTERS = [
  { v: '', l: 'Todos' },
  { v: 'rent', l: 'Arrendamento' },
  { v: 'sale', l: 'Venda' },
]

function ListingCard({ listing, onPress }) {
  const roleColors = {
    owner: { color: '#059669', bg: 'rgba(5,150,105,0.1)', label: 'Proprietário' },
    micheiro: { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', label: 'Micheiro' },
    agent: { color: '#6366f1', bg: 'rgba(99,102,241,0.1)', label: 'Agente' },
  }
  const role = roleColors[listing.lister_role] || roleColors.owner

  return (
    <button onClick={() => onPress(listing)}
      style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden', textAlign: 'left', cursor: 'pointer', width: '100%', display: 'block', padding: 0 }}>
      {/* Cover image */}
      <div style={{ height: 180, background: '#1E1E1E', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {listing.cover_image
          ? <img src={listing.cover_image} alt={listing.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
            </svg>
        }
        {/* Role badge */}
        <div style={{ position: 'absolute', top: 10, left: 10, background: role.bg, border: `1px solid ${role.color}40`, borderRadius: 20, padding: '3px 10px' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: role.color }}>{role.label}</span>
        </div>
        {/* Save count */}
        {listing.saves_count > 0 && (
          <div style={{ position: 'absolute', top: 10, right: 10, background: 'rgba(0,0,0,0.6)', borderRadius: 20, padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 4 }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#FFFFFF" stroke="none"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#FFFFFF' }}>{listing.saves_count}</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ padding: '12px 14px 14px' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {listing.title}
        </p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
          </svg>
          {listing.location_display}
        </p>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>
            {listing.formatted_price || `${Number(listing.price).toLocaleString()} Kz`}
          </span>
          {listing.price_negotiable && (
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', fontStyle: 'italic' }}>Negociável</span>
          )}
        </div>
      </div>
    </button>
  )
}

function FilterSheet({ visible, onClose, filters, onApply }) {
  const [local, setLocal] = useState(filters)

  if (!visible) return null

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: '#141414', borderRadius: '20px 20px 0 0', border: '1px solid #1E1E1E', padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto', maxHeight: '80vh', overflow: 'auto' }}>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A', margin: '0 auto 20px' }} />
        <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 20 }}>Filtros</h3>

        {/* Price range */}
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Preço (Kz)</p>
          <div style={{ display: 'flex', gap: 10 }}>
            <input type="number" placeholder="Mínimo" value={local.min_price || ''}
              onChange={e => setLocal(p => ({ ...p, min_price: e.target.value }))}
              style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', color: '#FFFFFF', fontSize: 13, outline: 'none' }} />
            <input type="number" placeholder="Máximo" value={local.max_price || ''}
              onChange={e => setLocal(p => ({ ...p, max_price: e.target.value }))}
              style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', color: '#FFFFFF', fontSize: 13, outline: 'none' }} />
          </div>
        </div>

        {/* Bedrooms (property) */}
        {(!local.category || local.category === 'property') && (
          <div style={{ marginBottom: 20 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Quartos mínimo</p>
            <div style={{ display: 'flex', gap: 8 }}>
              {[1, 2, 3, 4, 5].map(n => (
                <button key={n} onClick={() => setLocal(p => ({ ...p, bedrooms: p.bedrooms === n ? '' : n }))}
                  style={{ width: 44, height: 44, borderRadius: 10, border: `1.5px solid ${local.bedrooms === n ? '#C9A84C' : '#2A2A2A'}`, background: local.bedrooms === n ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: local.bedrooms === n ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                  {n}+
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Lister role */}
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#9A9A9A', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Tipo de anunciante</p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {[{ v: '', l: 'Todos' }, { v: 'owner', l: 'Proprietário' }, { v: 'micheiro', l: 'Micheiro' }, { v: 'agent', l: 'Agente' }].map(opt => (
              <button key={opt.v} onClick={() => setLocal(p => ({ ...p, lister_role: opt.v }))}
                style={{ padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${local.lister_role === opt.v ? '#C9A84C' : '#2A2A2A'}`, background: local.lister_role === opt.v ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: local.lister_role === opt.v ? '#C9A84C' : '#FFFFFF', cursor: 'pointer' }}>
                {opt.l}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => { setLocal({}); onApply({}) }}
            style={{ flex: 1, padding: '12px 0', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', cursor: 'pointer' }}>
            Limpar
          </button>
          <button onClick={() => { onApply(local); onClose() }}
            style={{ flex: 2, padding: '12px 0', borderRadius: 12, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            Aplicar filtros
          </button>
        </div>
      </div>
    </div>
  )
}

export default function RentalsPage() {
  const navigate = useNavigate()
  const [listings, setListings] = useState([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('')
  const [purpose, setPurpose] = useState('')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({})
  const [showFilters, setShowFilters] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)

  const loadListings = useCallback(async (reset = false) => {
    try {
      if (reset) setLoading(true)
      const params = new URLSearchParams()
      if (category) params.set('category', category)
      if (purpose) params.set('purpose', purpose)
      if (search) params.set('search', search)
      if (filters.min_price) params.set('min_price', filters.min_price)
      if (filters.max_price) params.set('max_price', filters.max_price)
      if (filters.bedrooms) params.set('bedrooms', filters.bedrooms)
      if (filters.lister_role) params.set('lister_role', filters.lister_role)
      params.set('page', reset ? 1 : page)

      const res = await client.get(`/api/rentals/browse/?${params}`)
      const data = res.data.results || res.data || []
      if (reset) {
        setListings(data)
        setPage(2)
      } else {
        setListings(prev => [...prev, ...data])
        setPage(p => p + 1)
      }
      setHasMore(data.length >= 10)
    } catch (err) {
      console.error('Rentals load failed:', err)
    } finally {
      setLoading(false)
    }
  }, [category, purpose, search, filters, page])

  useEffect(() => {
    loadListings(true)
  }, [category, purpose, filters])

  useEffect(() => {
    const t = setTimeout(() => loadListings(true), 400)
    return () => clearTimeout(t)
  }, [search])

  return (
    <BuyerLayout>
      <FilterSheet visible={showFilters} onClose={() => setShowFilters(false)}
        filters={filters} onApply={f => { setFilters(f); loadListings(true) }} />

      {/* Header */}
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 14 }}>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 2 }}>MICHA</p>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>Imóveis & Alugueres</h1>
          </div>
          <button onClick={() => navigate('/rentals/create')}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 12, border: '1px solid rgba(201,168,76,0.3)', background: 'rgba(201,168,76,0.1)', cursor: 'pointer' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#C9A84C' }}>Anunciar</span>
          </button>
        </div>

        {/* Search */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '11px 14px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar por zona, tipo..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }} />
          </div>
          <button onClick={() => setShowFilters(true)}
            style={{ width: 46, height: 46, borderRadius: 14, border: `1.5px solid ${Object.keys(filters).length > 0 ? '#C9A84C' : '#2A2A2A'}`, background: Object.keys(filters).length > 0 ? 'rgba(201,168,76,0.1)' : '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={Object.keys(filters).length > 0 ? '#C9A84C' : '#9A9A9A'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="6" x2="20" y2="6" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="11" y1="18" x2="13" y2="18" />
            </svg>
          </button>
        </div>

        {/* Category tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {CATEGORY_TABS.map(tab => (
            <button key={tab.v} onClick={() => setCategory(tab.v)}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 50, flexShrink: 0, border: `1.5px solid ${category === tab.v ? '#C9A84C' : '#2A2A2A'}`, background: category === tab.v ? 'rgba(201,168,76,0.1)' : '#1E1E1E', cursor: 'pointer' }}>
              <span style={{ fontSize: 14 }}>{tab.icon}</span>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: category === tab.v ? 600 : 400, color: category === tab.v ? '#C9A84C' : '#9A9A9A' }}>{tab.l}</span>
            </button>
          ))}
        </div>

        {/* Purpose filter */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
          {PURPOSE_FILTERS.map(f => (
            <button key={f.v} onClick={() => setPurpose(f.v)}
              style={{ padding: '5px 14px', borderRadius: 50, border: `1px solid ${purpose === f.v ? '#C9A84C' : '#2A2A2A'}`, background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: purpose === f.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      {/* Listings */}
      <div className="screen" style={{ flex: 1 }}
        onScroll={e => {
          const { scrollTop, scrollHeight, clientHeight } = e.target
          if (scrollHeight - scrollTop - clientHeight < 200 && hasMore && !loading) {
            loadListings(false)
          }
        }}>
        <div style={{ padding: '12px 16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {loading && listings.length === 0 ? (
            Array(3).fill(0).map((_, i) => (
              <div key={i} style={{ background: '#141414', borderRadius: 16, height: 260, animation: 'pulse 1.5s ease-in-out infinite' }}>
                <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
              </div>
            ))
          ) : listings.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 32px', gap: 16 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>
                Sem anúncios disponíveis para os critérios seleccionados.
              </p>
              <button onClick={() => { setCategory(''); setPurpose(''); setFilters({}); setSearch('') }}
                style={{ padding: '10px 20px', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', cursor: 'pointer' }}>
                Limpar filtros
              </button>
            </div>
          ) : (
            listings.map(listing => (
              <ListingCard key={listing.id} listing={listing}
                onPress={l => navigate(`/rentals/${l.id}`)} />
            ))
          )}
        </div>
      </div>
    </BuyerLayout>
  )
}
