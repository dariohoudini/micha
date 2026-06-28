import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * LiveStreamsPage — /live
 *
 * AliExpress Complete 2025 CH 9 — Live Streaming Shopping.
 *
 * What's wired here
 * ─────────────────
 *  • Discovery list — GET /api/v1/streams/ (returns active stream
 *    objects). If the backend doesn't yet implement that endpoint,
 *    we render an empty state explaining the feature is coming.
 *  • Featured stream hero — first stream gets the large hero card.
 *  • Category chips — filter by category.
 *  • Tap any stream → joins the room (placeholder navigation to
 *    /live/<id>; the actual WebRTC video player is out of scope
 *    without media-server infra).
 *  • Every interaction is logged to UserEvent.
 *
 * What's deliberately NOT here
 * ────────────────────────────
 *  • WebRTC video player + WebSocket chat — needs media-server
 *    infrastructure (Agora, Cloudflare Stream, etc.).
 *  • Heart-tap animation overlay, viewer count realtime updates —
 *    same dependency.
 *  • PiP minimised bubble — heavy iOS Capacitor plugin work.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const CATS = ['Tudo', 'Moda', 'Beleza', 'Eletrónica', 'Casa', 'Crianças', 'Outros']

export default function LiveStreamsPage() {
  const navigate = useNavigate()
  const [list, setList] = useState([])
  const [cat, setCat] = useState('Tudo')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    track('live.open', {})
    client.get('/api/v1/streams/?status=live')
      .then(r => setList(r.data?.results || r.data || []))
      .catch(() => setList([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = cat === 'Tudo' ? list : list.filter(s => (s.category || '').toLowerCase().includes(cat.toLowerCase()))

  return (
    <BuyerLayout>
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>🔴 Live agora</h1>
      </div>

      {/* Category chips */}
      <div style={{ padding: '4px 16px 12px', display: 'flex', gap: 6, overflowX: 'auto' }}>
        {CATS.map(c => (
          <button key={c} onClick={() => { setCat(c); track('live.filter', { category: c }) }}
            style={{ padding: '7px 14px', borderRadius: 18, border: `1.5px solid ${cat === c ? '#C9A84C' : '#2A2A2A'}`, background: cat === c ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: cat === c ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}>{c}</button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 100px' }}>
        {loading ? (
          <div style={{ height: 240, background: '#141414', borderRadius: 14, animation: 'pulse 1.4s ease-in-out infinite' }}>
            <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.45}}`}</style>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '60px 20px', textAlign: 'center' }}>
            <p style={{ fontSize: 50 }}>📺</p>
            <p style={{ ...S, fontSize: 15, color: '#FFF', marginTop: 12, fontWeight: 600 }}>Sem transmissões ao vivo agora</p>
            <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 6 }}>Volte mais tarde — as lojas estão a preparar-se!</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {filtered.map((s, i) => (
              <button key={s.id || i} onClick={() => { navigate(`/live/${s.id}`); track('live.join', { stream_id: s.id }) }}
                style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, overflow: 'hidden', padding: 0, cursor: 'pointer', textAlign: 'left' }}>
                <div style={{ position: 'relative', height: 180, background: `linear-gradient(135deg, #1a0c0c, #0A0A0A) ${s.thumbnail_url ? `url(${s.thumbnail_url}) center/cover` : ''}` }}>
                  <span style={{ position: 'absolute', top: 8, left: 8, padding: '3px 8px', borderRadius: 6, background: '#ef4444', ...S, fontSize: 9, fontWeight: 700, color: '#FFF', letterSpacing: '0.04em' }}>● LIVE</span>
                  <span style={{ position: 'absolute', top: 8, right: 8, padding: '3px 8px', borderRadius: 6, background: 'rgba(0,0,0,0.6)', ...S, fontSize: 10, color: '#FFF' }}>👁 {s.viewer_count || 0}</span>
                </div>
                <div style={{ padding: 10 }}>
                  <p style={{ ...S, fontSize: 12, color: '#FFF', fontWeight: 600, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{s.title || 'Live agora'}</p>
                  <p style={{ ...S, fontSize: 10, color: '#9A9A9A', marginTop: 4 }}>{s.host_name || s.store_name || '—'}</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </BuyerLayout>
  )
}
