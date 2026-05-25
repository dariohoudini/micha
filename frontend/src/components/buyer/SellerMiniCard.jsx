/**
 * SellerMiniCard — seller summary widget for PDP and order detail.
 *
 * Surfaces the seller's identity + R4 trust badge + response time +
 * a one-tap "Chat" CTA. Shipped where the buyer is making a trust
 * decision: at the bottom of the PDP (post-spec, pre-CTA) and on
 * order-detail pages (between buyer and seller comms).
 *
 * Props
 * ─────
 *   store               { id, name, slug, owner, badge_level, ... }
 *   trustBadge          override badge_level if not on store object
 *   responseTime        human string ("Responde em ~2h")
 *   onChatClick         override default chat-navigation behaviour
 *   onStoreClick        override default store-navigation behaviour
 *
 * a11y
 * ─────
 *   role="region" + aria-label
 *   each CTA has visible text + aria-label
 */
import { useNavigate } from 'react-router-dom'
import SellerTrustChip from './SellerTrustChip'


export default function SellerMiniCard({
  store,
  trustBadge,
  responseTime,
  onChatClick,
  onStoreClick,
}) {
  const navigate = useNavigate()
  if (!store) return null

  const name = store.name || store.title || 'Vendedor'
  const badgeLevel = trustBadge || store.badge_level || store.trust_badge
                  || (store.is_verified ? 'verified' : null)

  const goStore = () => {
    if (onStoreClick) return onStoreClick()
    const target = store.slug ? `/store/${store.slug}` : `/store/${store.id}`
    navigate(target)
  }

  const goChat = () => {
    if (onChatClick) return onChatClick()
    // Existing chat conversation pattern: /chat/<conversationId> OR
    // start-with-store via store id. Fallback: store page.
    if (store.id) navigate(`/chat/new?store=${store.id}`)
    else goStore()
  }

  return (
    <section
      role="region"
      aria-label={`Vendedor: ${name}`}
      style={{
        background: '#141414',
        border: '1px solid #1E1E1E',
        borderRadius: 14, padding: 14,
        display: 'flex', alignItems: 'center', gap: 12,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      {/* Avatar / icon */}
      <button
        type="button"
        onClick={goStore}
        aria-label={`Abrir loja ${name}`}
        style={{
          width: 48, height: 48, borderRadius: 12,
          background: '#1E1E1E', border: '1px solid #2A2A2A',
          flexShrink: 0, display: 'flex', alignItems: 'center',
          justifyContent: 'center', cursor: 'pointer',
          overflow: 'hidden', padding: 0,
        }}
      >
        {store.logo || store.image_url ? (
          <img
            src={store.logo || store.image_url}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <span aria-hidden="true" style={{ fontSize: 20 }}>🏪</span>
        )}
      </button>

      {/* Identity + badge */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <button
          type="button"
          onClick={goStore}
          style={{
            background: 'none', border: 'none', padding: 0,
            cursor: 'pointer', textAlign: 'left', width: '100%',
            color: '#FFFFFF',
          }}
        >
          <div style={{
            fontSize: 14, fontWeight: 600, color: '#FFFFFF',
            overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', marginBottom: 4,
          }}>
            {name}
          </div>
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {badgeLevel && (
            <SellerTrustChip level={badgeLevel} size="sm" />
          )}
          {responseTime && (
            <span style={{
              fontSize: 11, color: '#9A9A9A',
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}>
              <span aria-hidden="true">⚡</span>
              {responseTime}
            </span>
          )}
        </div>
      </div>

      {/* Chat CTA */}
      <button
        type="button"
        onClick={goChat}
        aria-label={`Conversar com ${name}`}
        style={{
          padding: '10px 14px', borderRadius: 10,
          background: 'rgba(99, 102, 241, 0.12)',
          border: '1px solid rgba(99, 102, 241, 0.35)',
          color: '#A5B4FC',
          fontSize: 12, fontWeight: 600,
          cursor: 'pointer', flexShrink: 0,
          minHeight: 40, display: 'flex', alignItems: 'center', gap: 6,
          fontFamily: 'inherit',
        }}
      >
        <span aria-hidden="true">💬</span>
        Chat
      </button>
    </section>
  )
}
