import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * SaleEventBanner — AliExpress Complete 2025 CH 17.3.
 *
 * Drop-in on Home. Polls /api/v1/promotions/sale-events/ once on
 * mount; if any major event is live, renders a full-width hero
 * carousel above the regular banner carousel. Auto-rotates if more
 * than one event is active. Tap = deep-link via ``cta_url`` (which
 * the admin sets to e.g. ``/promotions/1111-2026`` or any URL).
 *
 * Renders nothing if no events are live, so always safe to include.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

function Countdown({ endsAt }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const ms = Math.max(0, new Date(endsAt).getTime() - now)
  const d = Math.floor(ms / 86_400_000)
  const h = Math.floor((ms % 86_400_000) / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return (
    <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
      {d > 0 ? `${d}d ` : ''}{String(h).padStart(2, '0')}:{String(m).padStart(2, '0')}:{String(s).padStart(2, '0')}
    </span>
  )
}

export default function SaleEventBanner() {
  const navigate = useNavigate()
  const [events, setEvents] = useState([])
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    client.get('/api/v1/promotions/sale-events/')
      .then(r => setEvents(r.data?.results || r.data || []))
      .catch(() => setEvents([]))
  }, [])

  useEffect(() => {
    if (events.length <= 1) return
    const t = setInterval(() => setIdx(i => (i + 1) % events.length), 4500)
    return () => clearInterval(t)
  }, [events.length])

  if (!events.length) return null
  const e = events[idx]
  const ctaTap = () => {
    track('home.sale_event_tap', { event_id: e.id, slug: e.slug })
    if (e.cta_url) {
      if (e.cta_url.startsWith('http')) window.open(e.cta_url, '_blank')
      else navigate(e.cta_url)
    } else {
      navigate('/flash-sale')
    }
  }

  return (
    <button onClick={ctaTap}
      style={{
        display: 'block', width: 'calc(100% - 32px)', margin: '0 16px 12px',
        background: e.banner_image ? `url(${e.banner_image}) center/cover` : `linear-gradient(135deg, ${e.bg_color || '#C9A84C'}, #0A0A0A)`,
        border: 'none', borderRadius: 14, padding: '18px 20px', textAlign: 'left',
        color: '#FFFFFF', cursor: 'pointer', overflow: 'hidden', position: 'relative',
      }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ ...S, fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', opacity: 0.85 }}>{e.name}</p>
          <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, marginTop: 4 }}>{e.headline || 'Mega promoção'}</p>
          {e.subheading && <p style={{ ...S, fontSize: 12, opacity: 0.85, marginTop: 4 }}>{e.subheading}</p>}
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 12 }}>
          <p style={{ ...S, fontSize: 10, opacity: 0.7 }}>Termina em</p>
          <Countdown endsAt={e.ends_at} />
        </div>
      </div>
      <div style={{ marginTop: 12, display: 'inline-flex', padding: '6px 14px', borderRadius: 20, background: 'rgba(0,0,0,0.35)', ...S, fontSize: 11, fontWeight: 700 }}>
        {e.cta_label || 'Ver ofertas'} →
      </div>
      {events.length > 1 && (
        <div style={{ display: 'flex', gap: 4, position: 'absolute', bottom: 8, right: 12 }}>
          {events.map((_, i) => (
            <span key={i} style={{ width: i === idx ? 16 : 5, height: 5, borderRadius: 3, background: i === idx ? '#FFFFFF' : 'rgba(255,255,255,0.4)' }} />
          ))}
        </div>
      )}
    </button>
  )
}
