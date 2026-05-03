import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reviewsAPI } from '@/api/reviews'
import { useAuthStore } from '@/stores/authStore'

const S = { fontFamily: "'DM Sans',sans-serif" }

function Stars({ rating, size = 12, interactive = false, onRate }) {
  const [hover, setHover] = useState(0)
  const display = hover || rating
  return (
    <div style={{ display: 'flex', gap: 2 }} role={interactive ? 'radiogroup' : undefined} aria-label={interactive ? 'Avaliação' : undefined}>
      {[1, 2, 3, 4, 5].map(i => (
        <button key={i}
          onClick={() => interactive && onRate?.(i)}
          onMouseEnter={() => interactive && setHover(i)}
          onMouseLeave={() => interactive && setHover(0)}
          disabled={!interactive}
          style={{ background: 'none', border: 'none', padding: 0, cursor: interactive ? 'pointer' : 'default', lineHeight: 0 }}
          aria-label={interactive ? `${i} estrela${i > 1 ? 's' : ''}` : undefined}
        >
          <svg width={size} height={size} viewBox="0 0 24 24" fill={i <= display ? '#C9A84C' : 'none'} stroke="#C9A84C" strokeWidth="1.5">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          </svg>
        </button>
      ))}
    </div>
  )
}

function RatingBar({ stars, count, total }) {
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ ...S, fontSize: 11, color: '#9A9A9A', width: 8, flexShrink: 0 }}>{stars}</span>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C" style={{ flexShrink: 0 }}><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
      <div style={{ flex: 1, height: 5, background: '#1E1E1E', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: '#C9A84C', borderRadius: 3, transition: 'width 0.5s ease' }} />
      </div>
      <span style={{ ...S, fontSize: 11, color: '#9A9A9A', width: 24, textAlign: 'right', flexShrink: 0 }}>{count}</span>
    </div>
  )
}

function ReviewCard({ review, onHelpful, onReport }) {
  const [expanded, setExpanded] = useState(false)
  const text = review.comment || review.text || ''
  const needsClamp = text.length > 180
  const display = (!expanded && needsClamp) ? text.slice(0, 180) + '…' : text
  const date = review.created_at ? new Date(review.created_at).toLocaleDateString('pt-AO', { day: '2-digit', month: 'short', year: 'numeric' }) : ''

  return (
    <div style={{ paddingBottom: 16, borderBottom: '1px solid #1E1E1E', marginBottom: 16 }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'linear-gradient(135deg,#C9A84C,#A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, overflow: 'hidden' }}>
          {review.reviewer?.avatar
            ? <img src={review.reviewer.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            : <span style={{ ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A' }}>
                {(review.reviewer?.full_name || review.reviewer?.username || 'A').slice(0, 1).toUpperCase()}
              </span>
          }
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ ...S, fontSize: 13, fontWeight: 600, color: '#FFF' }}>
              {review.reviewer?.full_name || review.reviewer?.username || 'Comprador'}
            </span>
            {review.is_verified_purchase && (
              <span style={{ ...S, fontSize: 9, fontWeight: 600, color: '#059669', background: 'rgba(5,150,105,0.1)', padding: '1px 6px', borderRadius: 4 }}>Compra verificada</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3 }}>
            <Stars rating={review.rating} size={11} />
            <span style={{ ...S, fontSize: 10, color: '#9A9A9A' }}>{date}</span>
          </div>
        </div>
      </div>

      {review.title && (
        <p style={{ ...S, fontSize: 13, fontWeight: 600, color: '#FFF', marginBottom: 4 }}>{review.title}</p>
      )}
      <p style={{ ...S, fontSize: 13, color: '#CCCCCC', lineHeight: 1.6 }}>{display}</p>
      {needsClamp && (
        <button onClick={() => setExpanded(!expanded)}
          style={{ ...S, fontSize: 12, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginTop: 4 }}>
          {expanded ? 'Ver menos' : 'Ver mais'}
        </button>
      )}

      {/* Photos */}
      {review.images?.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginTop: 10, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {review.images.map((img, i) => (
            <img key={i} src={img.url || img} alt="" style={{ width: 72, height: 72, borderRadius: 8, objectFit: 'cover', flexShrink: 0, border: '1px solid #2A2A2A' }} />
          ))}
        </div>
      )}

      {/* Seller reply */}
      {review.reply && (
        <div style={{ marginTop: 10, background: '#141414', borderRadius: 10, padding: '10px 12px', borderLeft: '3px solid #C9A84C' }}>
          <p style={{ ...S, fontSize: 11, fontWeight: 600, color: '#C9A84C', marginBottom: 4 }}>Resposta do vendedor</p>
          <p style={{ ...S, fontSize: 12, color: '#CCCCCC', lineHeight: 1.5 }}>{review.reply}</p>
        </div>
      )}

      {/* Helpful / Report */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
        <button onClick={() => onHelpful?.(review.id)}
          style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'none', border: '1px solid #2A2A2A', borderRadius: 8, padding: '4px 10px', cursor: 'pointer' }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z" /><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" /></svg>
          <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>Útil {review.helpful_count > 0 ? `(${review.helpful_count})` : ''}</span>
        </button>
        <button onClick={() => onReport?.(review.id)}
          style={{ ...S, fontSize: 11, color: '#9A9A9A', background: 'none', border: 'none', cursor: 'pointer' }}>
          Reportar
        </button>
      </div>
    </div>
  )
}

function WriteReviewModal({ productId, onClose, onSuccess }) {
  const [rating, setRating] = useState(0)
  const [title, setTitle] = useState('')
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => {
      if (rating === 0) { setError('Selecciona uma avaliação.'); throw new Error('rating') }
      if (!comment.trim()) { setError('Escreve um comentário.'); throw new Error('comment') }
      const fd = new FormData()
      fd.append('product', productId)
      fd.append('rating', rating)
      fd.append('title', title)
      fd.append('comment', comment)
      return reviewsAPI.createProductReview(fd)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reviews', productId] })
      onSuccess?.()
      onClose()
    },
    onError: (e) => { if (e.message !== 'rating' && e.message !== 'comment') setError('Erro ao enviar avaliação.') },
  })

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 480, background: '#141414', borderRadius: '20px 20px 0 0', padding: '24px 20px', paddingBottom: 'max(28px,env(safe-area-inset-bottom))', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontFamily: "'Playfair Display',serif", fontSize: 18, fontWeight: 700, color: '#FFF' }}>Avaliar produto</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <Stars rating={rating} size={36} interactive onRate={r => { setRating(r); setError('') }} />
          <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>
            {['', 'Muito mau', 'Mau', 'Razoável', 'Bom', 'Excelente'][rating] || 'Toca para avaliar'}
          </p>
        </div>

        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Título (opcional)"
          style={{ background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 14px', ...S, fontSize: 13, color: '#FFF', outline: 'none' }} />
        <textarea value={comment} onChange={e => setComment(e.target.value)} placeholder="Partilha a tua experiência…" rows={4}
          style={{ background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 14px', ...S, fontSize: 13, color: '#FFF', outline: 'none', resize: 'none', lineHeight: 1.5 }} />

        {error && <p style={{ ...S, fontSize: 12, color: '#ef4444' }}>{error}</p>}

        <button onClick={() => mutation.mutate()} disabled={mutation.isPending}
          style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: mutation.isPending ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          {mutation.isPending ? 'A enviar…' : 'Publicar avaliação'}
        </button>
      </div>
    </div>
  )
}

export default function ReviewsSection({ productId }) {
  const [sort, setSort] = useState('recent')
  const [filterRating, setFilterRating] = useState(0)
  const [showWrite, setShowWrite] = useState(false)
  const isAuth = useAuthStore(s => s.isAuth)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['reviews', productId, sort, filterRating],
    queryFn: () => reviewsAPI.getProductReviews(productId, { ordering: sort === 'recent' ? '-created_at' : sort === 'helpful' ? '-helpful_count' : 'rating', rating: filterRating || undefined }),
    enabled: !!productId,
    select: r => r.data,
  })

  const ratingData = useQuery({
    queryKey: ['reviews', productId, 'rating'],
    queryFn: () => reviewsAPI.getProductRating(productId).then(r => r.data),
    enabled: !!productId,
  })

  const markHelpful = useMutation({
    mutationFn: (id) => reviewsAPI.voteHelpful(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviews', productId] }),
  })

  const reviews = data?.results || data || []
  const summary = ratingData.data || {}
  const totalCount = summary.count || data?.count || reviews.length
  const avgRating = summary.average || 0
  const breakdown = summary.breakdown || {}

  return (
    <div>
      {/* Rating summary */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <span style={{ fontFamily: "'Playfair Display',serif", fontSize: 42, fontWeight: 700, color: '#FFF', lineHeight: 1 }}>
            {avgRating > 0 ? avgRating.toFixed(1) : '—'}
          </span>
          <Stars rating={avgRating} size={13} />
          <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>{totalCount} avaliações</span>
        </div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}>
          {[5, 4, 3, 2, 1].map(n => (
            <RatingBar key={n} stars={n} count={breakdown[n] || 0} total={totalCount} />
          ))}
        </div>
      </div>

      {/* Filters + sort */}
      <div style={{ display: 'flex', gap: 6, overflowX: 'auto', scrollbarWidth: 'none', marginBottom: 16 }}>
        {[0, 5, 4, 3].map(n => (
          <button key={n} onClick={() => setFilterRating(n)}
            style={{ padding: '5px 12px', borderRadius: 20, flexShrink: 0, border: `1px solid ${filterRating === n ? '#C9A84C' : '#2A2A2A'}`, background: filterRating === n ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, color: filterRating === n ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
            {n === 0 ? 'Todas' : `${n}★`}
          </button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexShrink: 0 }}>
          {[{ v: 'recent', l: 'Recentes' }, { v: 'helpful', l: 'Úteis' }, { v: 'rating', l: 'Nota' }].map(o => (
            <button key={o.v} onClick={() => setSort(o.v)}
              style={{ padding: '5px 12px', borderRadius: 20, border: `1px solid ${sort === o.v ? '#C9A84C' : '#2A2A2A'}`, background: sort === o.v ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 11, color: sort === o.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              {o.l}
            </button>
          ))}
        </div>
      </div>

      {/* Write review CTA */}
      {isAuth && (
        <button onClick={() => setShowWrite(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '12px 14px', borderRadius: 12, border: '1px dashed #2A2A2A', background: 'transparent', cursor: 'pointer', marginBottom: 20 }}>
          <Stars rating={0} size={18} />
          <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Escreve a tua avaliação…</span>
        </button>
      )}

      {/* Reviews list */}
      {isLoading ? (
        Array.from({ length: 3 }).map((_, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 10 }}>
              <div className="skeleton" style={{ width: 36, height: 36, borderRadius: '50%', flexShrink: 0 }} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="skeleton" style={{ height: 12, width: '40%', borderRadius: 5 }} />
                <div className="skeleton" style={{ height: 10, width: '25%', borderRadius: 5 }} />
              </div>
            </div>
            <div className="skeleton" style={{ height: 60, borderRadius: 8 }} />
          </div>
        ))
      ) : reviews.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>Ainda sem avaliações. Sê o primeiro!</p>
        </div>
      ) : (
        reviews.map(r => (
          <ReviewCard key={r.id} review={r} onHelpful={(id) => markHelpful.mutate(id)} />
        ))
      )}

      {showWrite && <WriteReviewModal productId={productId} onClose={() => setShowWrite(false)} />}
    </div>
  )
}
