/**
 * PushPermissionPrompt — custom pre-prompt for push notification opt-in.
 *
 * Why a custom pre-prompt (NOT the OS dialog directly)
 * ─────────────────────────────────────────────────────
 * Industry research: showing the OS push dialog at app launch produces
 * ~30% opt-in. Showing a custom pre-prompt FIRST that explains the
 * value, THEN triggering the OS dialog only for users who tap "Yes",
 * roughly DOUBLES the opt-in rate (~60%+). Crucially: once a user
 * taps "No" on the OS dialog, they can NEVER be re-prompted by iOS.
 * The first ask is the only ask — so we make it count.
 *
 * When to mount this
 * ──────────────────
 *   ✓ OrderConfirmedPage (peak intent moment)
 *   ✓ NotificationsPage on first open (relevance)
 *   ✓ Day-2 return banner (high engagement signal)
 *   ✗ App splash / login / first explore (cold ask, kills opt-in)
 *
 * Auto-skips
 * ──────────
 *   • shouldAskPushPermission() returns false (already asked or not native)
 *   • current permission state is already 'granted' or 'denied' — both
 *     are terminal from our side
 */
import { useEffect, useState } from 'react'
import {
  requestPushPermission,
  shouldAskPushPermission,
} from '@/hooks/usePushNotifications'


export default function PushPermissionPrompt({ context = 'order' }) {
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!shouldAskPushPermission()) return
    // Slight delay so the prompt doesn't compete with celebration
    // animations / immediate page paint.
    const t = setTimeout(() => setVisible(true), 1200)
    return () => clearTimeout(t)
  }, [])

  if (!visible) return null

  const handleEnable = async () => {
    setBusy(true)
    try {
      await requestPushPermission()
    } catch {}
    finally {
      setBusy(false)
      setVisible(false)
    }
  }

  const handleDecline = () => {
    // Record that we asked without going to the OS — same as denying,
    // so we don't keep nagging. usePushNotifications.shouldAsk reads
    // PUSH_ASKED_LS; set it directly here without OS round-trip.
    try { localStorage.setItem('micha-push-asked-v1', '1') } catch {}
    setVisible(false)
  }

  const COPY = {
    order: {
      title: 'Acompanha o teu pedido',
      body: 'Receber notificações quando o vendedor confirmar, despachar e entregar o teu pedido.',
    },
    notifications: {
      title: 'Não percas atualizações',
      body: 'Activar notificações para receberes alertas em tempo real sobre pedidos, mensagens e ofertas.',
    },
    default: {
      title: 'Activar notificações',
      body: 'Recebe alertas importantes sobre a tua conta directamente no telefone.',
    },
  }
  const copy = COPY[context] || COPY.default

  return (
    <div
      role="dialog"
      aria-labelledby="push-prompt-title"
      aria-describedby="push-prompt-desc"
      style={{
        background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(99, 102, 241, 0.04) 100%)',
        border: '1px solid rgba(99, 102, 241, 0.3)',
        borderRadius: 14, padding: 16, marginBottom: 16,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div aria-hidden="true" style={{
          fontSize: 28, lineHeight: 1, flexShrink: 0,
        }}>🔔</div>
        <div style={{ flex: 1 }}>
          <h3 id="push-prompt-title" style={{
            margin: 0, fontSize: 14, fontWeight: 700, color: '#A5B4FC',
            marginBottom: 4,
          }}>
            {copy.title}
          </h3>
          <p id="push-prompt-desc" style={{
            margin: '0 0 12px', fontSize: 12, color: '#C7D2FE',
            lineHeight: 1.5,
          }}>
            {copy.body}
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              onClick={handleEnable}
              disabled={busy}
              style={{
                background: '#6366F1', color: 'white', border: 'none',
                padding: '8px 16px', borderRadius: 8,
                fontSize: 12, fontWeight: 700, cursor: 'pointer',
                minHeight: 36,
              }}
            >
              Activar
            </button>
            <button
              type="button"
              onClick={handleDecline}
              disabled={busy}
              style={{
                background: 'transparent', color: '#C7D2FE',
                border: '1px solid rgba(99, 102, 241, 0.3)',
                padding: '8px 16px', borderRadius: 8,
                fontSize: 12, fontWeight: 600, cursor: 'pointer',
                minHeight: 36,
              }}
            >
              Agora não
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
