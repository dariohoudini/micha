/**
 * ErrorState — recoverable error display with retry CTA.
 *
 * Variants
 * ────────
 *   network    no connection / fetch failed
 *   forbidden  403 — auth / permission issue
 *   not_found  404 — resource gone
 *   server     5xx — backend bug
 *   generic    unknown error
 *
 * Each variant ships with default copy (pt-AO + en fallback). Override
 * via the ``title`` / ``description`` props when a more specific
 * message helps.
 *
 * Always include ``onRetry`` so users have a recovery path. Without it
 * the component renders without the button — but that's a code smell
 * (errors users can't recover from need a different UI altogether).
 *
 * a11y: role="alert" so screen readers announce the error.
 */
import { useTranslation } from 'react-i18next'


const DEFAULT_COPY = {
  network: {
    icon: '📡',
    title: 'Sem ligação',
    description: 'Verifica a tua ligação à internet e tenta novamente.',
  },
  forbidden: {
    icon: '🚫',
    title: 'Sem permissão',
    description: 'Não tens acesso a este recurso. Contacta o suporte se achas que é um erro.',
  },
  not_found: {
    icon: '🔍',
    title: 'Não encontrado',
    description: 'O recurso que procuras já não existe ou foi removido.',
  },
  server: {
    icon: '⚠️',
    title: 'Algo correu mal',
    description: 'Estamos a trabalhar para resolver. Tenta de novo em alguns instantes.',
  },
  generic: {
    icon: '⚠️',
    title: 'Erro inesperado',
    description: 'Algo não correu como esperado. Tenta de novo.',
  },
}


export function errorVariantFromStatus(status) {
  if (status === 401 || status === 403) return 'forbidden'
  if (status === 404) return 'not_found'
  if (status >= 500) return 'server'
  if (status === 0 || status === undefined) return 'network'
  return 'generic'
}


export default function ErrorState({
  variant = 'generic',
  title,
  description,
  onRetry,
  retryLabel,
  compact = false,
  inline = false,
  detail,  // optional verbose detail for support tickets
}) {
  const copy = DEFAULT_COPY[variant] || DEFAULT_COPY.generic
  const finalTitle = title || copy.title
  const finalDescription = description || copy.description

  const styles = inline ? inlineStyles : fullStyles(compact)

  return (
    <div role="alert" aria-live="polite" style={styles.root}>
      {!inline && (
        <div aria-hidden="true" style={styles.icon}>{copy.icon}</div>
      )}
      <div style={styles.text}>
        <div style={styles.title}>{finalTitle}</div>
        <div style={styles.description}>{finalDescription}</div>
        {detail && (
          <details style={styles.details}>
            <summary style={styles.detailsSummary}>Detalhes técnicos</summary>
            <code style={styles.detailsCode}>{detail}</code>
          </details>
        )}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={styles.button}
        >
          {retryLabel || 'Tentar novamente'}
        </button>
      )}
    </div>
  )
}


const fullStyles = (compact) => ({
  root: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: compact ? '32px 24px' : '64px 32px',
    gap: 16,
    textAlign: 'center',
  },
  icon: { fontSize: 48, lineHeight: 1 },
  text: { display: 'flex', flexDirection: 'column', gap: 6 },
  title: {
    fontSize: 17, fontWeight: 700, color: '#E2E8F0',
  },
  description: {
    fontSize: 14, color: '#94A3B8', maxWidth: 320, lineHeight: 1.5,
  },
  button: {
    background: '#6366F1', color: 'white', border: 'none',
    padding: '10px 22px', borderRadius: 10, fontWeight: 600,
    fontSize: 14, cursor: 'pointer',
    minHeight: 44,  // a11y: touch target ≥44×44
  },
  details: {
    marginTop: 8, fontSize: 11, color: '#64748B',
  },
  detailsSummary: { cursor: 'pointer', userSelect: 'none' },
  detailsCode: {
    display: 'block', marginTop: 6, padding: 8,
    background: '#0D0D1A', border: '1px solid #1A1A2E',
    borderRadius: 6, textAlign: 'left',
    fontFamily: 'monospace', fontSize: 10,
    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  },
})


const inlineStyles = {
  root: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '10px 14px',
    background: 'rgba(239, 68, 68, 0.1)',
    border: '1px solid rgba(239, 68, 68, 0.25)',
    borderRadius: 10,
    color: '#FCA5A5',
  },
  icon: { display: 'none' },
  text: { flex: 1, display: 'flex', flexDirection: 'column', gap: 2 },
  title: { fontSize: 13, fontWeight: 600 },
  description: { fontSize: 12, color: '#F87171', opacity: 0.85 },
  button: {
    background: 'transparent',
    border: '1px solid #F8717155',
    color: '#F87171',
    padding: '6px 12px', borderRadius: 6,
    fontSize: 12, fontWeight: 600, cursor: 'pointer',
    minHeight: 32,
  },
  details: { display: 'none' },
  detailsSummary: {},
  detailsCode: {},
}
