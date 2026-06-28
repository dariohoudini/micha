import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * ReviewWritePage — AliExpress Complete 2025 CH 15.2.
 *
 * Multi-product review flow: an order may contain several items —
 * the buyer reviews one per step. Each step has:
 *   • 5-star rating (required, unlocks rest of form)
 *   • Star labels (Terrible / Bad / OK / Good / Excellent)
 *   • Optional review title (max 80)
 *   • Optional body (max 1000)
 *   • Photos (max 9)
 *   • Video (max 1, max 60s)  — file picker only; no length check FE
 *   • Anonymous checkbox  — flips ``is_anonymous`` on submission
 *   • Per-coin reward hint: 5 / 10 / 20 based on attachments
 *
 * Backend: posts to /api/v1/reviews/ with FormData. Coins are
 * credited via the existing coin-task hook (post_review) — see
 * CoinTaskCompletion model in apps.loyalty.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }
const input = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 14, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }
const STAR_LABELS = ['Terrível', 'Mau', 'Razoável', 'Bom', 'Excelente']

export default function ReviewWritePage() {
  const navigate = useNavigate()
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [stepIdx, setStepIdx] = useState(0)
  const [reviews, setReviews] = useState({})  // by product_id
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const photoRef = useRef()
  const videoRef = useRef()

  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }

  useEffect(() => {
    track('review.open', { order_id: orderId })
    client.get(`/api/v1/orders/${orderId}/`).then(r => setOrder(r.data)).catch(() => {})
  }, [orderId])

  const items = order?.items || []
  const item = items[stepIdx]
  const productId = item?.product?.id || item?.product || item?.product_id
  const r = (productId && reviews[productId]) || { rating: 0, title: '', body: '', photos: [], video: null, anonymous: false }

  const setR = (patch) => setReviews(prev => ({ ...prev, [productId]: { ...r, ...patch } }))

  const coinHint = (() => {
    if (r.video) return 20
    if ((r.photos || []).length > 0) return 10
    if (r.body?.trim().length >= 10) return 5
    return 0
  })()

  const submitOne = async () => {
    if (!r.rating) { show('Escolha 1-5 estrelas.', 'error'); return }
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('order_id', orderId)
      fd.append('product_id', productId)
      fd.append('rating', String(r.rating))
      if (r.title) fd.append('title', r.title)
      if (r.body) fd.append('body', r.body)
      if (r.anonymous) fd.append('is_anonymous', 'true')
      ;(r.photos || []).forEach((p, i) => fd.append(`photo_${i}`, p.file, p.file.name))
      if (r.video) fd.append('video', r.video.file, r.video.file.name)
      await client.post('/api/v1/reviews/', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      track('review.submitted', { product_id: productId, rating: r.rating, has_photo: (r.photos || []).length > 0, has_video: !!r.video, anonymous: !!r.anonymous })
      // Coins task post (best-effort; backend may enforce caps).
      try { await client.post('/api/v1/loyalty/coins/tasks/complete/', { task: 'post_review' }) } catch {}
      // Advance to next product OR finish.
      if (stepIdx + 1 < items.length) {
        setStepIdx(stepIdx + 1)
        show('Avaliação enviada!')
      } else {
        show('Todas as avaliações enviadas!')
        setTimeout(() => navigate(`/orders/${orderId}`), 900)
      }
    } catch (e) {
      show(e.response?.data?.detail || 'Erro ao submeter.', 'error')
    } finally { setBusy(false) }
  }

  const skip = () => {
    track('review.skipped', { product_id: productId })
    if (stepIdx + 1 < items.length) setStepIdx(stepIdx + 1)
    else navigate(`/orders/${orderId}`)
  }

  if (!order) return <BuyerLayout><div style={{ padding: 40, textAlign: 'center' }}><p style={{ ...S, color: '#9A9A9A' }}>A carregar…</p></div></BuyerLayout>

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>Avaliar pedido</h1>
        <span style={{ ...S, fontSize: 11, color: '#9A9A9A', marginLeft: 'auto' }}>{stepIdx + 1}/{items.length}</span>
      </div>
      {/* Step indicator */}
      <div style={{ display: 'flex', gap: 4, padding: '0 16px 8px' }}>
        {items.map((_, i) => (
          <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i < stepIdx ? '#10b981' : i === stepIdx ? '#C9A84C' : '#1E1E1E' }} />
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 120px' }}>
        {/* Product card */}
        <div style={{ display: 'flex', gap: 12, padding: 12, background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, marginBottom: 16 }}>
          <div style={{ width: 60, height: 60, borderRadius: 10, background: '#1E1E1E', flexShrink: 0 }}>
            {item?.product_thumbnail && <img src={item.product_thumbnail} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 10 }} />}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ ...S, fontSize: 13, color: '#FFF', fontWeight: 600, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{item?.product_title || item?.title}</p>
            <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>Qtd: {item?.quantity || 1}</p>
          </div>
        </div>

        {/* Stars */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginBottom: 8 }}>
          {[1, 2, 3, 4, 5].map(n => (
            <button key={n} onClick={() => setR({ rating: n })}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 36, color: n <= r.rating ? '#C9A84C' : '#2A2A2A' }}>★</button>
          ))}
        </div>
        {r.rating > 0 && (
          <p style={{ ...S, fontSize: 12, color: '#C9A84C', textAlign: 'center', marginBottom: 16 }}>{STAR_LABELS[r.rating - 1]}</p>
        )}

        {r.rating > 0 && (
          <>
            <div style={{ marginBottom: 12 }}>
              <input value={r.title || ''} onChange={e => setR({ title: e.target.value.slice(0, 80) })}
                placeholder="Resumo (opcional)" maxLength={80} style={input} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <textarea value={r.body || ''} onChange={e => setR({ body: e.target.value.slice(0, 1000) })}
                placeholder="Conte mais sobre o produto…" rows={4} maxLength={1000}
                style={{ ...input, resize: 'vertical' }} />
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>{(r.body || '').length}/1000</p>
            </div>

            {/* Photos */}
            <div style={{ marginBottom: 12 }}>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 6 }}>Fotos (max 9) · +5 moedas</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                {(r.photos || []).map((p, i) => (
                  <div key={i} style={{ position: 'relative', aspectRatio: '1', borderRadius: 8, overflow: 'hidden', background: '#1E1E1E' }}>
                    <img src={p.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    <button onClick={() => setR({ photos: r.photos.filter((_, j) => j !== i) })}
                      style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', background: 'rgba(0,0,0,0.8)', border: 'none', color: '#FFF', cursor: 'pointer', ...S, fontSize: 10 }}>✕</button>
                  </div>
                ))}
                {(r.photos || []).length < 9 && (
                  <button onClick={() => photoRef.current?.click()}
                    style={{ aspectRatio: '1', background: '#141414', border: '2px dashed #2A2A2A', borderRadius: 8, color: '#9A9A9A', cursor: 'pointer', ...S, fontSize: 22 }}>+</button>
                )}
              </div>
              <input ref={photoRef} type="file" accept="image/*" multiple style={{ display: 'none' }}
                onChange={e => {
                  const files = Array.from(e.target.files || []).slice(0, 9 - (r.photos || []).length)
                  setR({ photos: [...(r.photos || []), ...files.map(f => ({ file: f, url: URL.createObjectURL(f) }))] })
                  e.target.value = ''
                }} />
            </div>

            {/* Video */}
            <div style={{ marginBottom: 12 }}>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginBottom: 6 }}>Vídeo (max 60s, MP4) · +20 moedas</p>
              {r.video ? (
                <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', background: '#1E1E1E' }}>
                  <video src={r.video.url} controls style={{ width: '100%', display: 'block', maxHeight: 200 }} />
                  <button onClick={() => setR({ video: null })}
                    style={{ position: 'absolute', top: 8, right: 8, background: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: 6, padding: '4px 8px', ...S, fontSize: 11, color: '#FFF', cursor: 'pointer' }}>Remover</button>
                </div>
              ) : (
                <button onClick={() => videoRef.current?.click()}
                  style={{ width: '100%', padding: 12, background: '#141414', border: '2px dashed #2A2A2A', borderRadius: 10, ...S, fontSize: 12, color: '#9A9A9A', cursor: 'pointer' }}>
                  + Adicionar vídeo
                </button>
              )}
              <input ref={videoRef} type="file" accept="video/mp4,video/*" style={{ display: 'none' }}
                onChange={e => { const f = e.target.files?.[0]; if (f) setR({ video: { file: f, url: URL.createObjectURL(f) } }); e.target.value = '' }} />
            </div>

            {/* Anonymous */}
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, cursor: 'pointer' }}>
              <input type="checkbox" checked={!!r.anonymous} onChange={e => setR({ anonymous: e.target.checked })} />
              <span style={{ ...S, fontSize: 13, color: '#FFF' }}>Publicar como "Comprador MICHA" (anónimo)</span>
            </label>

            {/* Coin hint */}
            <div style={{ marginTop: 12, padding: 10, background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.25)', borderRadius: 10, textAlign: 'center' }}>
              <p style={{ ...S, fontSize: 12, color: '#C9A84C', fontWeight: 700 }}>🪙 Ganha {coinHint > 0 ? coinHint : 5} moedas{coinHint > 0 ? '' : ' (com texto)'}</p>
            </div>
          </>
        )}
      </div>

      <div style={{ padding: '12px 16px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', borderTop: '1px solid #1A1A1A', background: '#0A0A0A', display: 'flex', gap: 10 }}>
        <button onClick={skip}
          style={{ flex: 1, padding: '13px 0', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 13, color: '#9A9A9A', cursor: 'pointer' }}>
          Saltar este
        </button>
        <button onClick={submitOne} disabled={busy || !r.rating}
          style={{ flex: 2, padding: '13px 0', borderRadius: 12, border: 'none', background: r.rating ? '#C9A84C' : '#2A2A2A', ...S, fontSize: 13, fontWeight: 700, color: r.rating ? '#0A0A0A' : '#555', cursor: r.rating ? 'pointer' : 'not-allowed' }}>
          {busy ? 'A enviar…' : (stepIdx + 1 < items.length ? 'Submeter e próximo' : 'Submeter avaliação')}
        </button>
      </div>
    </BuyerLayout>
  )
}
