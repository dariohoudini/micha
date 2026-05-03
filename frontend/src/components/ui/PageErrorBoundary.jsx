import { Component } from 'react'
import Button from './Button'

export default class PageErrorBoundary extends Component {
  state = { hasError: false, error: null }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[PageErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div
        role="alert"
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '32px 24px',
          gap: 16,
          textAlign: 'center',
          background: '#0A0A0A',
        }}
      >
        <div style={{
          width: 64, height: 64, borderRadius: 18,
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>

        <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>
          Algo correu mal
        </p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', maxWidth: 260, lineHeight: 1.5 }}>
          Ocorreu um erro inesperado. Tente novamente ou volte à página anterior.
        </p>

        {import.meta.env.DEV && this.state.error && (
          <pre style={{
            fontFamily: 'monospace', fontSize: 10, color: '#ef4444',
            background: 'rgba(239,68,68,0.05)', padding: 12, borderRadius: 8,
            maxWidth: '100%', overflow: 'auto', textAlign: 'left', maxHeight: 120,
          }}>
            {this.state.error.toString()}
          </pre>
        )}

        <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
          <Button
            variant="surface"
            size="md"
            onClick={() => window.history.back()}
          >
            Voltar
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Tentar novamente
          </Button>
        </div>
      </div>
    )
  }
}
