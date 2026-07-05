/**
 * frontend/src/lib/guestProfile.js
 * ─────────────────────────────────
 *
 * First-Run doc CH10/CH11 — the client side of the PII-free guest
 * profile. A stable device id anchors a server-side guest profile that
 * captures the setup answers (locale, interests, permissions) BEFORE
 * any account, and carries onto the account at signup.
 *
 * The device id is generated once and stored in localStorage; the same
 * value is passed to /auth/register so the backend can copy the guest
 * profile onto the new user (carry-over).
 *
 * All calls are best-effort and swallow errors — onboarding personalises
 * if it works and costs nothing if it doesn't (never block the feed).
 */
import client from '@/api/client'

const DEVICE_KEY = 'micha_device_id_v1'

export function getDeviceId() {
  try {
    let id = localStorage.getItem(DEVICE_KEY)
    if (!id) {
      id = (crypto?.randomUUID?.() ||
            'dev-' + Math.random().toString(36).slice(2) + Date.now().toString(36))
      localStorage.setItem(DEVICE_KEY, id)
    }
    return id
  } catch {
    // Storage blocked (private mode) — a per-session id still works.
    return 'dev-ephemeral-' + Date.now().toString(36)
  }
}

/** Bootstrap the guest session (Screen 1). Returns the guest profile. */
export async function bootstrapGuest(attribution) {
  try {
    const res = await client.post('/api/v1/guest/session/', {
      device_id: getDeviceId(),
      ...(attribution ? { attribution } : {}),
    })
    return res?.data?.guest || null
  } catch { return null }
}

/** Write a setup answer to the guest profile (Screens 2–5). */
export async function patchGuestProfile(patch) {
  try {
    const res = await client.patch('/api/v1/guest/profile/', {
      device_id: getDeviceId(), ...patch,
    })
    return res?.data || null
  } catch { return null }
}

/** Mark onboarding complete/skipped (Screen 6) so a returning guest
 *  skips setup and lands on the feed. */
export async function completeOnboarding(skipped = false) {
  try {
    await client.post('/api/v1/onboarding/complete/', {
      device_id: getDeviceId(), skipped,
    })
  } catch { /* never block */ }
}
