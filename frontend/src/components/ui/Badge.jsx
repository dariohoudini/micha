const VARIANTS = {
  gold:    { bg: 'rgba(201,168,76,0.12)',   color: '#C9A84C',  border: 'rgba(201,168,76,0.25)' },
  success: { bg: 'rgba(5,150,105,0.12)',    color: '#059669',  border: 'rgba(5,150,105,0.3)' },
  danger:  { bg: 'rgba(239,68,68,0.12)',    color: '#ef4444',  border: 'rgba(239,68,68,0.3)' },
  warning: { bg: 'rgba(245,158,11,0.12)',   color: '#f59e0b',  border: 'rgba(245,158,11,0.3)' },
  info:    { bg: 'rgba(59,130,246,0.12)',   color: '#3b82f6',  border: 'rgba(59,130,246,0.3)' },
  muted:   { bg: 'rgba(255,255,255,0.05)',  color: '#9A9A9A',  border: '#2A2A2A' },
  purple:  { bg: 'rgba(139,92,246,0.12)',   color: '#8b5cf6',  border: 'rgba(139,92,246,0.3)' },
}

const SIZES = {
  xs: { fontSize: 10, padding: '2px 6px', borderRadius: 6 },
  sm: { fontSize: 11, padding: '3px 8px', borderRadius: 8 },
  md: { fontSize: 12, padding: '4px 10px', borderRadius: 10 },
}

export default function Badge({
  children,
  variant = 'muted',
  size = 'sm',
  dot = false,
  style = {},
}) {
  const v = VARIANTS[variant] || VARIANTS.muted
  const s = SIZES[size] || SIZES.sm

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontFamily: "'DM Sans', sans-serif",
        fontWeight: 700,
        lineHeight: 1,
        background: v.bg,
        color: v.color,
        border: `1px solid ${v.border}`,
        ...s,
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width: 6, height: 6, borderRadius: '50%',
            background: v.color, flexShrink: 0,
          }}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  )
}

export function StatusBadge({ status }) {
  const MAP = {
    pending:    { label: 'Pendente',    variant: 'warning' },
    confirmed:  { label: 'Confirmado',  variant: 'info' },
    processing: { label: 'A processar', variant: 'info' },
    shipped:    { label: 'Enviado',     variant: 'purple' },
    delivered:  { label: 'Entregue',    variant: 'success' },
    cancelled:  { label: 'Cancelado',   variant: 'danger' },
    refunded:   { label: 'Reembolsado', variant: 'muted' },
    active:     { label: 'Activo',      variant: 'success' },
    inactive:   { label: 'Inactivo',    variant: 'muted' },
    suspended:  { label: 'Suspenso',    variant: 'danger' },
    open:       { label: 'Aberto',      variant: 'danger' },
    resolved:   { label: 'Resolvido',   variant: 'success' },
  }
  const cfg = MAP[status?.toLowerCase()] || { label: status, variant: 'muted' }
  return <Badge variant={cfg.variant} dot>{cfg.label}</Badge>
}
