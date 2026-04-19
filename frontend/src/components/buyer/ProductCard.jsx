import { useState } from 'react'
import { formatPrice } from './mockData'

export default function ProductCard({ product, onPress, size = 'normal' }) {
  const [wishlist, setWishlist] = useState(false)
  const discount = product.original_price
    ? Math.round((1 - product.price / product.original_price) * 100)
    : null

  const isSmall = size === 'small'

  return (
    <div
      onClick={() => onPress?.(product)}
      style={{
        background: '#1E1E1E',
        borderRadius: 16,
        overflow: 'hidden',
        border: '1px solid #2A2A2A',
        cursor: 'pointer',
        transition: 'transform 0.15s ease, border-color 0.2s ease',
        position: 'relative',
        width: isSmall ? 150 : '100%',
        flexShrink: 0,
      }}
      onMouseDown={e => e.currentTarget.style.transform = 'scale(0.97)'}
      onMouseUp={e => e.currentTarget.style.transform = 'scale(1)'}
      onTouchStart={e => e.currentTarget.style.transform = 'scale(0.97)'}
      onTouchEnd={e => e.currentTarget.style.transform = 'scale(1)'}
    >
      {/* Image area */}
      <div style={{
        height: isSmall ? 140 : 180,
        background: product.image_color,
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {/* Placeholder product visual */}
        <div style={{
          width: isSmall ? 60 : 80,
          height: isSmall ? 60 : 80,
          borderRadius: '50%',
          background: 'rgba(255,255,255,0.08)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width={isSmall ? 28 : 36} height={isSmall ? 28 : 36} viewBox="0 0 24 24"
            fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </div>

        {/* Badge */}
        {product.badge && (
          <div style={{
            position: 'absolute', top: 10, left: 10,
            background: product.badge_color,
            color: product.badge_color === '#C9A84C' ? '#0A0A0A' : '#FFFFFF',
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 10, fontWeight: 700,
            padding: '3px 8px', borderRadius: 6,
            letterSpacing: '0.03em',
          }}>
            {product.badge}
          </div>
        )}

        {/* Express badge */}
        {product.express && (
          <div style={{
            position: 'absolute', bottom: 10, left: 10,
            background: 'rgba(201,168,76,0.15)',
            border: '1px solid rgba(201,168,76,0.4)',
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', borderRadius: 6,
          }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
            <span style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 9, fontWeight: 700, color: '#C9A84C', letterSpacing: '0.05em',
            }}>EXPRESS</span>
          </div>
        )}

        {/* Wishlist */}
        <button
          onClick={e => { e.stopPropagation(); setWishlist(v => !v) }}
          style={{
            position: 'absolute', top: 10, right: 10,
            width: 30, height: 30, borderRadius: '50%',
            background: 'rgba(0,0,0,0.5)',
            border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24"
            fill={wishlist ? '#C9A84C' : 'none'}
            stroke={wishlist ? '#C9A84C' : '#FFFFFF'} strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
          </svg>
        </button>
      </div>

      {/* Info */}
      <div style={{ padding: isSmall ? '10px 10px 12px' : '12px 12px 14px' }}>
        {/* Seller */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
          <span style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 10, color: '#9A9A9A',
          }}>
            {product.seller}
          </span>
          {product.seller_verified && (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C">
              <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
        </div>

        {/* Name */}
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: isSmall ? 12 : 13,
          fontWeight: 500,
          color: '#FFFFFF',
          lineHeight: 1.3,
          marginBottom: 8,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          {product.name}
        </p>

        {/* Price row */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
          <span style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: isSmall ? 13 : 15,
            fontWeight: 700,
            color: '#C9A84C',
          }}>
            {formatPrice(product.price)}
          </span>
          {product.original_price && (
            <span style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 11, color: '#9A9A9A',
              textDecoration: 'line-through',
            }}>
              {formatPrice(product.original_price)}
            </span>
          )}
        </div>

        {/* Rating */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="#C9A84C">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          </svg>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>
            {product.rating} ({product.reviews})
          </span>
        </div>
      </div>
    </div>
  )
}
