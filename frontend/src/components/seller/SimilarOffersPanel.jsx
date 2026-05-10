import { useEffect, useRef, useState } from 'react'
import client from '@/api/client'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const S = { fontFamily: "'DM Sans', sans-serif" }

/**
 * SimilarOffersPanel — surfaces existing canonical ProductGroups that
 * a seller's draft listing would join.
 *
 * Goal: stop sellers from forking the catalog by listing the same product
 * under a slightly different title. When matches exist we offer them a
 * one-tap "Adicionar como oferta" that pre-fills the canonical title +
 * brand so their listing is auto-routed to the existing SPU.
 *
 * Props:
 *   title         — current draft title from the form
 *   brand         — current draft brand
 *   categorySlug  — current draft category slug
 *   onUseCanonical(group) — callback when seller chooses to list as offer
 */
export default function SimilarOffersPanel({ title, brand, categorySlug, onUseCanonical }) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const debounceRef = useRef(null)

  useEffect(() => {
    setDismissed(false)
  }, [title, brand, categorySlug])

  useEffect(() => {
    if (!title || title.trim().length < 4) {
      setResults([])
      return
    }
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setLoading(true)
      client.get('/api/v1/products/groups/suggest/', {
        params: { title: title.trim(), brand: (brand || '').trim(), category: categorySlug || '' },
      })
        .then(r => setResults(r.data?.results || []))
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 600)
    return () => clearTimeout(debounceRef.current)
  }, [title, brand, categorySlug])

  if (dismissed || results.length === 0) return null

  return (
    <div style={{
      background: 'rgba(59,130,246,0.06)',
      border: '1px solid rgba(59,130,246,0.25)',
      borderRadius: 14, padding: 14, marginTop: 12,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#60a5fa', margin: 0 }}>
            🏬 Este produto já está na MICHA
          </p>
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', margin: '2px 0 0', lineHeight: 1.5 }}>
            Adicione a sua oferta a um produto existente — os compradores comparam
            preços lado a lado e você apanha o tráfego das pesquisas.
          </p>
        </div>
        <button onClick={() => setDismissed(true)} aria-label="Dispensar"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9A9A9A', fontSize: 16, padding: 0, lineHeight: 1 }}>
          ×
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
        {results.map(g => (
          <button
            key={g.group_id}
            onClick={() => onUseCanonical?.(g)}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 12px', borderRadius: 10,
              background: '#141414', border: '1px solid #1E1E1E',
              cursor: 'pointer', textAlign: 'left', width: '100%',
            }}>
            <div style={{
              width: 40, height: 40, borderRadius: 8, overflow: 'hidden',
              background: '#1E1E1E', flexShrink: 0,
            }}>
              {g.best_offer_image && (
                <img src={g.best_offer_image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              )}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#FFF', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {g.title}
              </p>
              <p style={{ ...S, fontSize: 10, color: '#9A9A9A', margin: '2px 0 0' }}>
                {g.seller_count} {g.seller_count === 1 ? 'loja' : 'lojas'} · desde {fmt(g.best_price)}
              </p>
            </div>
            <span style={{ ...S, fontSize: 11, fontWeight: 700, color: '#60a5fa', flexShrink: 0 }}>
              Adicionar oferta →
            </span>
          </button>
        ))}
      </div>

      {loading && (
        <p style={{ ...S, fontSize: 10, color: '#555', margin: '8px 0 0', textAlign: 'center' }}>
          A procurar mais correspondências…
        </p>
      )}
    </div>
  )
}
