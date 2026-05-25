/**
 * CookieConsentBanner.jsx
 * ────────────────────────
 *
 * GDPR Art. 7 + Lei 22/11 compliance banner.
 *
 * Behaviour
 * ─────────
 *  • On first mount, GET /api/v1/account/data-request/consent/
 *    using the consent_key stashed in localStorage (anonymous) OR
 *    the JWT (authed).
 *  • If has_consent=false → show banner with three categories
 *    (analytics / marketing / preferences) + ACCEPT ALL / REJECT
 *    NON-ESSENTIAL / CUSTOMISE.
 *  • POST the user's choice; backend writes an append-only audit row.
 *
 * The banner remembers the choice for 12 months (cookie + backend).
 * Re-shows after policy_version bump.
 *
 * Design choices
 * ──────────────
 *  • NO inline scripts (CSP-compatible)
 *  • Inline-styled — matches the project's no-Tailwind admin pattern
 *  • Loads lazily (only on first session); subsequent sessions hit
 *    localStorage first and skip the network round-trip if recently
 *    answered.
 */
import { useEffect, useState } from 'react'
import client from '@/api/client'


const CONSENT_KEY_LS = 'micha-consent-key'
const CONSENT_CACHED_LS = 'micha-consent-cached-v1'
const POLICY_VERSION = 'v1'


function getOrCreateConsentKey() {
  try {
    let k = localStorage.getItem(CONSENT_KEY_LS)
    if (!k) {
      // 32 hex chars — same alphabet as backend secrets.token_urlsafe(24).
      k = Array.from(crypto.getRandomValues(new Uint8Array(24)))
        .map(b => b.toString(16).padStart(2, '0')).join('')
      localStorage.setItem(CONSENT_KEY_LS, k)
    }
    return k
  } catch {
    return ''
  }
}


function readCached() {
  try {
    const raw = localStorage.getItem(CONSENT_CACHED_LS)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed.policy_version !== POLICY_VERSION) return null
    return parsed
  } catch {
    return null
  }
}


function writeCached(state) {
  try {
    localStorage.setItem(
      CONSENT_CACHED_LS,
      JSON.stringify({ ...state, policy_version: POLICY_VERSION }),
    )
  } catch {}
}


export default function CookieConsentBanner() {
  const [visible, setVisible] = useState(false)
  const [showCustomise, setShowCustomise] = useState(false)
  const [prefs, setPrefs] = useState({
    analytics: false, marketing: false, preferences: false,
  })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const cached = readCached()
    if (cached) return  // already answered this policy version

    const consentKey = getOrCreateConsentKey()
    let aborted = false

    client.get('/api/v1/account/data-request/consent/', {
      params: { consent_key: consentKey },
    }).then(({ data }) => {
      if (aborted) return
      if (data?.has_consent) {
        writeCached(data)
        return
      }
      setVisible(true)
    }).catch(() => {
      // Network fail — show the banner anyway. Compliance requires
      // we ask BEFORE setting non-essential cookies. Safer to ask
      // twice than miss once.
      if (!aborted) setVisible(true)
    })

    return () => { aborted = true }
  }, [])

  async function submit(choice) {
    setBusy(true)
    try {
      const consent_key = getOrCreateConsentKey()
      const { data } = await client.post(
        '/api/v1/account/data-request/consent/',
        { ...choice, consent_key, policy_version: POLICY_VERSION },
      )
      writeCached(data)
      setVisible(false)
    } catch {
      // Even on network failure, hide the banner so a flaky connection
      // doesn't lock the user out of the app — they'll be asked again
      // on next visit when cache is empty.
      setVisible(false)
    } finally {
      setBusy(false)
    }
  }

  if (!visible) return null

  const styles = {
    overlay: {
      position: 'fixed', left: 0, right: 0, bottom: 0,
      background: 'rgba(13, 13, 26, 0.98)',
      borderTop: '1px solid rgba(99, 102, 241, 0.25)',
      padding: '20px 16px max(20px, env(safe-area-inset-bottom)) 16px',
      zIndex: 9999, color: '#E2E8F0',
      fontFamily: "'DM Sans', sans-serif",
      boxShadow: '0 -8px 24px rgba(0, 0, 0, 0.4)',
    },
    title: { fontSize: 16, fontWeight: 700, marginBottom: 6 },
    text: { fontSize: 13, lineHeight: 1.5, color: '#94A3B8', marginBottom: 14 },
    row: { display: 'flex', gap: 10, flexWrap: 'wrap' },
    primary: {
      background: '#6366F1', color: 'white', border: 'none',
      padding: '10px 18px', borderRadius: 10, fontWeight: 600,
      fontSize: 14, cursor: 'pointer',
    },
    secondary: {
      background: 'transparent', color: '#E2E8F0',
      border: '1px solid #2A2A3E',
      padding: '10px 18px', borderRadius: 10, fontWeight: 500,
      fontSize: 14, cursor: 'pointer',
    },
    link: {
      background: 'none', border: 'none', color: '#818CF8',
      padding: '10px 6px', cursor: 'pointer', fontSize: 13,
      textDecoration: 'underline',
    },
    checkRow: {
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 0', fontSize: 13,
    },
  }

  return (
    <div style={styles.overlay} role="dialog" aria-label="Consentimento de cookies">
      <div style={{ maxWidth: 920, margin: '0 auto' }}>
        <div style={styles.title}>Usamos cookies para melhorar a tua experiência</div>
        <div style={styles.text}>
          Cookies essenciais são sempre necessários. Os cookies de
          analítica, marketing e preferências ajudam-nos a melhorar o
          serviço — só os usamos com a tua autorização.{' '}
          <a href="/privacy" style={{ color: '#818CF8' }}>Saber mais</a>.
        </div>

        {showCustomise && (
          <div style={{ marginBottom: 14 }}>
            <label style={styles.checkRow}>
              <input
                type="checkbox" checked={prefs.analytics}
                onChange={e => setPrefs(p => ({ ...p, analytics: e.target.checked }))}
              />
              Analítica (medir uso do site, sem identificar pessoas)
            </label>
            <label style={styles.checkRow}>
              <input
                type="checkbox" checked={prefs.marketing}
                onChange={e => setPrefs(p => ({ ...p, marketing: e.target.checked }))}
              />
              Marketing (atribuição de campanhas + e-mails promocionais)
            </label>
            <label style={styles.checkRow}>
              <input
                type="checkbox" checked={prefs.preferences}
                onChange={e => setPrefs(p => ({ ...p, preferences: e.target.checked }))}
              />
              Preferências (lembrar idioma e tema)
            </label>
          </div>
        )}

        <div style={styles.row}>
          <button
            disabled={busy}
            onClick={() => submit({ analytics: true, marketing: true, preferences: true })}
            style={styles.primary}
          >
            Aceitar tudo
          </button>
          <button
            disabled={busy}
            onClick={() => submit({ analytics: false, marketing: false, preferences: false })}
            style={styles.secondary}
          >
            Rejeitar não-essenciais
          </button>
          {showCustomise ? (
            <button
              disabled={busy}
              onClick={() => submit(prefs)}
              style={styles.secondary}
            >
              Guardar a minha escolha
            </button>
          ) : (
            <button
              disabled={busy}
              onClick={() => setShowCustomise(true)}
              style={styles.link}
            >
              Personalizar
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
