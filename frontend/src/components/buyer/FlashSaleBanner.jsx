import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import promotionsAPI from '@/api/promotions'

const fmt = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'

function useFlashSales() {
  return useQuery({
    queryKey: ['flash-sales'],
    queryFn: async () => {
      const res = await promotionsAPI.getActiveFlashSales()
      return res.data.results || res.data || []
    },
    staleTime: 60 * 1000,
    retry: 1,
  })
}

function useCountdown(endsAt) {
  const [remaining, setRemaining] = useState(0)

  useEffect(() => {
    if (!endsAt) return
    const update = () => {
      const diff = Math.max(0, new Date(endsAt) - Date.now())
      setRemaining(diff)
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [endsAt])

  const h = Math.floor(remaining / 3_600_000)
  const m = Math.floor((remaining % 3_600_000) / 60_000)
  const s = Math.floor((remaining % 60_000) / 1000)
  return { h, m, s, expired: remaining === 0 }
}

function CountdownUnit({ value, label }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 28 }}>
      <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 15, fontWeight: 700, color: '#FFF', lineHeight: 1 }}>
        {String(value).padStart(2, '0')}
      </span>
      <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 8, color: 'rgba(255,255,255,0.5)', marginTop: 1 }}>{label}</span>
    </div>
  )
}

function FlashSaleCard({ sale }) {
  const navigate = useNavigate()
  const { h, m, s, expired } = useCountdown(sale.end_time || sale.ends_at)
  if (expired) return null

  const discount = Math.round(sale.discount_percentage || sale.discount_pct || 0)
  const name = sale.product_title || sale.name || sale.product?.name || 'Flash Sale'
  const image = sale.product_thumbnail || sale.product?.image_url || sale.image_url
  const productId = sale.product_id || sale.product?.id

  return (
    <button
      onClick={() => productId ? navigate(`/product/${productId}`) : null}
      style={{
        width: 200, flexShrink: 0, borderRadius: 14, overflow: 'hidden',
        background: 'linear-gradient(135deg, #1a0a00, #2a1500)',
        border: '1px solid rgba(201,168,76,0.3)',
        textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column',
      }}
    >
      {/* Image */}
      <div style={{ height: 110, background: '#1E1E1E', position: 'relative', overflow: 'hidden' }}>
        {image
          ? <img src={image} alt={name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
          : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(201,168,76,0.2)" strokeWidth="1.5" strokeLinecap="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
            </div>
        }
        {discount > 0 && (
          <div style={{ position: 'absolute', top: 8, left: 8, background: '#dc2626', borderRadius: 6, padding: '3px 8px' }}>
            <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, fontWeight: 700, color: '#FFF' }}>-{discount}%</span>
          </div>
        )}
        <div style={{ position: 'absolute', top: 8, right: 8, background: '#C9A84C', borderRadius: 6, padding: '3px 7px', display: 'flex', alignItems: 'center', gap: 3 }}>
          <svg width="8" height="8" viewBox="0 0 24 24" fill="#0A0A0A"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
          <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>FLASH</span>
        </div>
      </div>

      <div style={{ padding: '8px 10px 10px', flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}>
        <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 12, color: '#FFF', fontWeight: 500, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.4 }}>
          {name}
        </p>

        {sale.sale_price != null && (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
            <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>
              {fmt(sale.sale_price)}
            </span>
            {sale.original_price && Number(sale.original_price) > Number(sale.sale_price) && (
              <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 10, color: '#9A9A9A', textDecoration: 'line-through' }}>
                {fmt(sale.original_price)}
              </span>
            )}
          </div>
        )}

        {/* Countdown */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(220,38,38,0.15)', borderRadius: 8, padding: '5px 8px', width: 'fit-content' }}>
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
          <CountdownUnit value={h} label="h" />
          <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, color: '#dc2626', fontWeight: 700, lineHeight: 1 }}>:</span>
          <CountdownUnit value={m} label="m" />
          <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, color: '#dc2626', fontWeight: 700, lineHeight: 1 }}>:</span>
          <CountdownUnit value={s} label="s" />
        </div>
      </div>
    </button>
  )
}

function SkeletonCard() {
  return (
    <div style={{ width: 200, flexShrink: 0, borderRadius: 14, overflow: 'hidden', background: '#141414', border: '1px solid #1E1E1E' }}>
      <div className="skeleton" style={{ height: 110 }} />
      <div style={{ padding: '8px 10px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="skeleton" style={{ height: 12, width: '85%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 12, width: '55%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 22, width: 90, borderRadius: 8, marginTop: 2 }} />
      </div>
    </div>
  )
}

export default function FlashSaleBanner() {
  const { data: sales = [], isLoading } = useFlashSales()

  if (!isLoading && sales.length === 0) return null

  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#dc2626', boxShadow: '0 0 6px #dc2626', animation: 'pulse-dot 1.2s ease-in-out infinite' }} />
          <h2 style={{ fontFamily: "'Playfair Display',serif", fontSize: 17, fontWeight: 700, color: '#FFF' }}>Flash Sales</h2>
          <style>{`@keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.6;transform:scale(1.3)}}`}</style>
        </div>
        <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: '#dc2626', fontWeight: 600 }}>AO VIVO</span>
      </div>
      <div style={{ display: 'flex', gap: 10, overflowX: 'auto', padding: '0 16px 4px', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)
          : sales.map(s => <FlashSaleCard key={s.id} sale={s} />)
        }
      </div>
    </div>
  )
}
