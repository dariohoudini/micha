const SIZES = {
  xs:  { box: 28, font: 12, radius: 8,  badge: 7  },
  sm:  { box: 36, font: 14, radius: 10, badge: 8  },
  md:  { box: 44, font: 16, radius: 12, badge: 10 },
  lg:  { box: 56, font: 20, radius: 14, badge: 12 },
  xl:  { box: 72, font: 26, radius: 18, badge: 14 },
  '2xl': { box: 88, font: 32, radius: 22, badge: 16 },
}

function getInitials(name = '', email = '') {
  if (name) {
    const parts = name.trim().split(' ')
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    return parts[0][0].toUpperCase()
  }
  return email?.[0]?.toUpperCase() || '?'
}

export default function Avatar({
  src,
  name,
  email,
  size = 'md',
  online,
  shape = 'circle',
  style = {},
  onClick,
}) {
  const s = SIZES[size] || SIZES.md
  const initials = getInitials(name, email)
  const borderRadius = shape === 'circle' ? '50%' : s.radius

  return (
    <div
      style={{
        position: 'relative',
        width: s.box,
        height: s.box,
        flexShrink: 0,
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick(e) : undefined}
    >
      {src ? (
        <img
          src={src}
          alt={name || email || 'Avatar'}
          style={{
            width: '100%', height: '100%',
            borderRadius, objectFit: 'cover',
          }}
          loading="lazy"
        />
      ) : (
        <div
          style={{
            width: '100%', height: '100%',
            borderRadius,
            background: 'linear-gradient(135deg, #C9A84C, #A67C35)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          aria-label={name || email}
        >
          <span style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: s.font,
            fontWeight: 700,
            color: '#0A0A0A',
          }}>
            {initials}
          </span>
        </div>
      )}

      {online !== undefined && (
        <span
          aria-label={online ? 'Online' : 'Offline'}
          style={{
            position: 'absolute',
            bottom: 0, right: 0,
            width: s.badge, height: s.badge,
            borderRadius: '50%',
            background: online ? '#059669' : '#555',
            border: '2px solid #0A0A0A',
          }}
        />
      )}
    </div>
  )
}
