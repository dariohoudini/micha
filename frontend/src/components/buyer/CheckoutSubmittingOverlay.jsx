/**
 * CheckoutSubmittingOverlay
 * ──────────────────────────
 * Full-screen blocker shown while the checkout POST is in flight.
 *
 * Why this exists
 * ───────────────
 * Multicaixa Express + card-payment confirmations take 5–15 seconds
 * on a typical Angolan 4G connection. Without a clear visual, users
 * believe the app is frozen and:
 *   • close the app (orphan order, double-charge risk)
 *   • tap the button again (idempotency saves us, but UX is broken)
 *   • back-button to checkout (state confusion)
 *
 * The overlay communicates that something is happening, that they
 * should NOT close the app, and gives reassurance that money is safe.
 *
 * a11y
 * ─────
 *   role="alertdialog" — announces immediately to screen readers
 *   aria-busy="true"
 *   focus moves into the overlay (so back-button is intercepted)
 */
import { useEffect, useRef } from 'react'


export default function CheckoutSubmittingOverlay({ open, message }) {
  const containerRef = useRef(null)
  const previouslyFocused = useRef(null)

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement
    setTimeout(() => containerRef.current?.focus(), 50)
    // Prevent ESC and back-gesture from dismissing. ESC is rebound to
    // a no-op while the request is in flight.
    const blockKeys = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
      }
    }
    document.addEventListener('keydown', blockKeys, true)
    return () => {
      document.removeEventListener('keydown', blockKeys, true)
      try { previouslyFocused.current?.focus?.() } catch {}
    }
  }, [open])

  if (!open) return null

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      role="alertdialog"
      aria-busy="true"
      aria-live="assertive"
      aria-label="A processar pagamento"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(10, 10, 10, 0.95)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: 24, gap: 20,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      {/* Spinner */}
      <div
        aria-hidden="true"
        style={{
          width: 56, height: 56,
          border: '4px solid rgba(201, 168, 76, 0.2)',
          borderTopColor: '#C9A84C',
          borderRadius: '50%',
          animation: 'checkout-spin 1s linear infinite',
        }}
      />
      <style>{`
        @keyframes checkout-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

      <div style={{ textAlign: 'center', maxWidth: 320 }}>
        <h2 style={{
          margin: 0, color: '#FFFFFF',
          fontSize: 18, fontWeight: 700, marginBottom: 8,
        }}>
          {message || 'A processar o teu pagamento'}
        </h2>
        <p style={{
          margin: 0, color: '#A1A1AA',
          fontSize: 14, lineHeight: 1.5,
        }}>
          <strong style={{ color: '#FBBF24' }}>Não feches a aplicação.</strong>
          {' '}
          Isto pode demorar até 15 segundos. O teu pagamento está seguro.
        </p>
      </div>

      <div style={{
        fontSize: 11, color: '#71717A',
        background: 'rgba(255, 255, 255, 0.05)',
        padding: '8px 16px', borderRadius: 999,
      }}>
        🔒 Ligação encriptada • MICHA Pagamento Seguro
      </div>
    </div>
  )
}
