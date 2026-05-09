import { useEffect, useState } from 'react'

const S = { fontFamily: "'DM Sans', sans-serif" }

const STATE_CONFIG = {
  awaiting_seller: {
    icon: '🛡️',
    title: 'Protegido pela MICHA',
    body: 'Se o vendedor não confirmar a tempo, és reembolsado automaticamente.',
    deadline_label: 'Vendedor deve confirmar em',
    color: '#3b82f6',
  },
  awaiting_ship: {
    icon: '🛡️',
    title: 'Protegido pela MICHA',
    body: 'Se o vendedor não enviar a tempo, és reembolsado automaticamente.',
    deadline_label: 'Envio deve ocorrer em',
    color: '#3b82f6',
  },
  in_transit: {
    icon: '🛡️',
    title: 'Protegido pela MICHA',
    body: 'Se a entrega falhar, marcamos como entregue e tens 60 dias para disputar.',
    deadline_label: 'Entrega esperada em',
    color: '#8b5cf6',
  },
  in_protection: {
    icon: '🛡️',
    title: 'Garantia ativa',
    body: 'Tens este tempo para devolver ou disputar este pedido se algo correr mal.',
    deadline_label: 'Garantia termina em',
    color: '#059669',
  },
  completed: {
    icon: '✓',
    title: 'Pedido finalizado',
    body: 'Janela de garantia encerrada.',
    deadline_label: null,
    color: '#9A9A9A',
  },
  broken: {
    icon: '⚠️',
    title: 'Pedido cancelado pela MICHA',
    body: 'O prazo lapsou e o pedido foi reembolsado automaticamente.',
    deadline_label: null,
    color: '#dc2626',
  },
  none: null,
}

function diffParts(targetMs) {
  const ms = targetMs - Date.now()
  if (ms <= 0) return null
  const total = Math.floor(ms / 1000)
  return {
    days: Math.floor(total / 86400),
    hours: Math.floor((total % 86400) / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  }
}

export default function BuyerProtectionBanner({ state, deadlineAt }) {
  const config = STATE_CONFIG[state]
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!deadlineAt) return
    const id = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [deadlineAt])

  if (!config) return null

  const targetMs = deadlineAt ? new Date(deadlineAt).getTime() : null
  const remaining = targetMs ? diffParts(targetMs) : null
  const showCountdown = config.deadline_label && remaining

  // Compact "2d 4h" or "3h 12m" or "8m 42s"
  const compact = remaining ? (
    remaining.days > 0
      ? `${remaining.days}d ${remaining.hours}h`
      : remaining.hours > 0
        ? `${remaining.hours}h ${String(remaining.minutes).padStart(2, '0')}m`
        : `${remaining.minutes}m ${String(remaining.seconds).padStart(2, '0')}s`
  ) : null

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12,
      padding: '14px 16px', borderRadius: 14,
      background: `${config.color}10`,
      border: `1px solid ${config.color}33`,
    }}>
      <span style={{ fontSize: 22, lineHeight: 1, flexShrink: 0 }}>{config.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <p style={{ ...S, fontSize: 13, fontWeight: 700, color: config.color, margin: 0 }}>
            {config.title}
          </p>
          {showCountdown && (
            <p style={{ ...S, fontSize: 12, fontWeight: 700, color: config.color, margin: 0, fontVariantNumeric: 'tabular-nums' }}>
              {compact}
            </p>
          )}
        </div>
        <p style={{ ...S, fontSize: 11, color: '#9A9A9A', margin: '3px 0 0', lineHeight: 1.5 }}>
          {config.body}
        </p>
        {showCountdown && (
          <p style={{ ...S, fontSize: 10, color: '#777', margin: '2px 0 0' }}>
            {config.deadline_label} {compact}
          </p>
        )}
      </div>
    </div>
  )
}
