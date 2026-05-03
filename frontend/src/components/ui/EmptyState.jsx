export default function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}) {
  return (
    <div
      role="status"
      aria-label={title}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: compact ? '32px 24px' : '64px 32px',
        gap: 12,
        textAlign: 'center',
      }}
    >
      {icon && (
        <div style={{
          width: compact ? 48 : 64,
          height: compact ? 48 : 64,
          borderRadius: compact ? 14 : 18,
          background: 'rgba(201,168,76,0.08)',
          border: '1px solid rgba(201,168,76,0.15)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 4,
        }}>
          {icon}
        </div>
      )}

      <p style={{
        fontFamily: "'Playfair Display', serif",
        fontSize: compact ? 16 : 18,
        fontWeight: 700,
        color: '#FFFFFF',
      }}>
        {title}
      </p>

      {description && (
        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 13,
          color: '#9A9A9A',
          lineHeight: 1.5,
          maxWidth: 260,
        }}>
          {description}
        </p>
      )}

      {action && (
        <div style={{ marginTop: 8 }}>
          {action}
        </div>
      )}
    </div>
  )
}
