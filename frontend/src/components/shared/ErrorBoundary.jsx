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
    console.error('MICHA ErrorBoundary caught:', error, info)
  }

  handleReset() {
    this.setState({ hasError: false, error: null })
    window.location.href = '/'
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{
        height: '100vh',
        background: '#0A0A0A',
        color: 'white',
        padding: 20,
        overflowY: 'auto',
        fontFamily: 'monospace',
        fontSize: 12,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <h2 style={{ color: '#EF4444', marginBottom: 16 }}>Algo correu mal</h2>
        <pre style={{
          color: '#ff6b6b',
          whiteSpace: 'pre-wrap',
          maxWidth: '100%',
          marginBottom: 24,
          fontSize: 11,
        }}>
          {String(this.state.error)}
        </pre>
        <button
          onClick={() => this.handleReset()}
          style={{
            padding: '12px 24px',
            background: '#C9A84C',
            color: '#000',
            border: 'none',
            borderRadius: 10,
            fontFamily: "'DM Sans'",
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Tentar novamente
        </button>
      </div>
    )
  }
}
