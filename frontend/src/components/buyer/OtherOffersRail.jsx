import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'
const S = { fontFamily: "'DM Sans', sans-serif" }
const PLAYFAIR = { fontFamily: "'Playfair Display', serif" }

function OfferRow({ offer, currentPrice }) {
  const navigate = useNavigate()
  const img = offer.thumbnail || offer.image_url || offer.images?.[0]?.image
  const offerPrice = Number(offer.price || 0)
  const savings = currentPrice && currentPrice > offerPrice
    ? Math.round((1 - offerPrice / currentPrice) * 100)
    : null

  return (
    <button
      onClick={() => navigate(`/product/${offer.id}`)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 14px', borderRadius: 12,
        background: '#141414', border: '1px solid #1E1E1E',
        cursor: 'pointer', textAlign: 'left', width: '100%',
      }}>
      <div style={{
        width: 48, height: 48, borderRadius: 8, overflow: 'hidden',
        background: '#1E1E1E', flexShrink: 0,
      }}>
        {img && <img src={img} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ ...S, fontSize: 12, fontWeight: 600, color: '#FFF', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {offer.store_name || 'Vendedor'}
        </p>
        {offer.condition && offer.condition !== 'new' && (
          <p style={{ ...S, fontSize: 10, color: '#9A9A9A', margin: '2px 0 0' }}>
            {offer.condition === 'used' ? 'Usado' : 'Recondicionado'}
          </p>
        )}
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#C9A84C', margin: 0 }}>
          {fmt(offerPrice)}
        </p>
        {savings && savings > 0 && (
          <p style={{ ...S, fontSize: 10, fontWeight: 600, color: '#059669', margin: '2px 0 0' }}>
            poupa {savings}%
          </p>
        )}
      </div>
    </button>
  )
}

/**
 * "Other offers" rail — competing sellers for the same canonical product.
 * Renders nothing if the product has no group or no other offers.
 *
 * Props:
 *   groupId           — product.product_group_id from the API
 *   currentProductId  — product.id (excluded from the offers list)
 *   currentPrice      — used to compute savings %
 */
export default function OtherOffersRail({ groupId, currentProductId, currentPrice }) {
  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!groupId) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    client.get(`/api/v1/products/groups/${groupId}/offers/`, {
      params: { exclude: currentProductId },
    })
      .then(r => { if (!cancelled) setOffers(r.data?.results || r.data || []) })
      .catch(() => { if (!cancelled) setOffers([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [groupId, currentProductId])

  if (!groupId || (loading === false && offers.length === 0)) return null

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ padding: '0 16px', marginBottom: 12, display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <h2 style={{ ...PLAYFAIR, fontSize: 17, fontWeight: 700, color: '#FFF', margin: 0 }}>
          🏬 Outras lojas
        </h2>
        {offers.length > 0 && (
          <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>
            {offers.length} {offers.length === 1 ? 'oferta' : 'ofertas'}
          </span>
        )}
      </div>
      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading ? (
          <>
            {[1, 2, 3].map(i => (
              <div key={i} className="skeleton" style={{ height: 72, borderRadius: 12 }} />
            ))}
          </>
        ) : (
          offers.map(o => (
            <OfferRow key={o.id} offer={o} currentPrice={currentPrice} />
          ))
        )}
      </div>
    </div>
  )
}
