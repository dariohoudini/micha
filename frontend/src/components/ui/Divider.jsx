export default function Divider({ label, style = {} }) {
  if (label) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, ...style }}>
        <div style={{ flex: 1, height: 1, background: '#2A2A2A' }} />
        <span style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 11,
          fontWeight: 600,
          color: '#555',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
        }}>
          {label}
        </span>
        <div style={{ flex: 1, height: 1, background: '#2A2A2A' }} />
      </div>
    )
  }

  return (
    <hr
      style={{
        border: 'none',
        borderTop: '1px solid #2A2A2A',
        margin: 0,
        ...style,
      }}
    />
  )
}
