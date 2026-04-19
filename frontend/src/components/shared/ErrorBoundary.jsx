import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    // In production replace with Sentry or similar
    if (import.meta.env.DEV) {
      console.error('MICHA ErrorBoundary caught:', error, info)
    }
  }

  handleReset() {
    this.setState({ hasError: false, error: null })
    window.location.href = '/'
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div style={{
        height: '100%', background: '#0A0A0A',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '0 32px', textAlign: 'center',
      }}>
        {/* Icon */}
        <div style={{
          width: 80, height: 80, borderRadius: 20,
          background: 'rgba(220,38,38,0.08)',
          border: '1px solid rgba(220,38,38,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: 24,
        }}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
            stroke="#dc2626" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>

        <h1 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 26, fontWeight: 700, color: '#FFFFFF',
          marginBottom: 10,
        }}>
          Algo correu mal
        </h1>

        <p style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 14, color: '#9A9A9A',
          lineHeight: 1.6, marginBottom: 32, maxWidth: 280,
        }}>
          Ocorreu um erro inesperado. Os nossos técnicos foram notificados.
        </p>

        <button
          onClick={() => this.handleReset()}
          style={{
            width: '100%', maxWidth: 320,
            padding: '14px', borderRadius: 14,
            background: '#C9A84C', border: 'none',
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 15, fontWeight: 600, color: '#0A0A0A',
            cursor: 'pointer',
          }}
        >
          Voltar ao início
        </button>

        {import.meta.env.DEV && this.state.error && (
          <pre style={{
            marginTop: 24, padding: 12, borderRadius: 8,
            background: '#141414', border: '1px solid #2A2A2A',
            fontFamily: 'monospace', fontSize: 11,
            color: '#dc2626', textAlign: 'left',
            maxWidth: '100%', overflow: 'auto',
            maxHeight: 120,
          }}>
            {this.state.error.toString()}
          </pre>
        )}
      </div>
    )
  }
}
