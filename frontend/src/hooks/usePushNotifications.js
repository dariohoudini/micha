/**
 * usePushNotifications — Capacitor push hook.
 *
 * R1 Sprint 3 UX pass: permission request is DEFERRED. Industry data
 * shows asking for push permission at app launch produces ~30% opt-in
 * rates; asking after a meaningful action (first order, opens
 * notification inbox, returns 2nd session) produces ~70%. Once a
 * user denies, the OS dialog NEVER re-prompts — so the first ask is
 * the only ask. Wasting it on a cold launch is malpractice.
 *
 * Public API
 * ──────────
 *   usePushNotifications({ onNotification })
 *       Mounts message + action listeners. Does NOT request
 *       permission. Safe to call from App root.
 *
 *   requestPushPermission()
 *       Trigger the OS permission dialog. Call from a high-intent
 *       moment: post-checkout success, on first opening of
 *       notifications page, after Day-2 return. Records the request
 *       in localStorage so we don't ask again in the same session.
 *
 *   shouldAskPushPermission()
 *       Returns true if we haven't asked yet this device. Use to
 *       gate a custom pre-prompt UI BEFORE calling the OS dialog
 *       (custom pre-prompts double the OS-dialog acceptance rate).
 */
import { useEffect } from 'react'
import { Capacitor } from '@capacitor/core'
import client from '@/api/client'


const PUSH_ASKED_LS = 'micha-push-asked-v1'
const isNative = () => {
  try { return Capacitor.isNativePlatform() } catch { return false }
}


async function registerFCMToken(token) {
  try {
    await client.post('/api/v1/notifications/push/register/', {
      token, platform: Capacitor.getPlatform(),
    })
  } catch {
    // Silent — token registration retries on next app open.
  }
}


export function shouldAskPushPermission() {
  if (!isNative()) return false
  try {
    return localStorage.getItem(PUSH_ASKED_LS) !== '1'
  } catch {
    return true
  }
}


/**
 * Trigger the OS push permission dialog. Call from a high-intent
 * moment (post-checkout, notification page open, day-2 return).
 *
 * @returns 'granted' | 'denied' | 'prompt' | 'unavailable'
 */
export async function requestPushPermission() {
  if (!isNative()) return 'unavailable'
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    const { receive } = await PushNotifications.requestPermissions()
    try { localStorage.setItem(PUSH_ASKED_LS, '1') } catch {}
    if (receive === 'granted') {
      await PushNotifications.register()
    }
    return receive
  } catch {
    return 'unavailable'
  }
}


export function usePushNotifications({ onNotification } = {}) {
  useEffect(() => {
    if (!isNative()) return

    let removeListeners = () => {}

    import('@capacitor/push-notifications').then(({ PushNotifications: PN }) => {
      // R1 Sprint 3: NO permission request here. Just listeners.
      // Permission must be requested by an explicit user-intent moment
      // via requestPushPermission().

      // For users who already granted previously, register() is safe
      // to call — it's idempotent and re-syncs the token if it rotated.
      try {
        // Check current permission state without prompting.
        PN.checkPermissions().then(({ receive }) => {
          if (receive === 'granted') {
            PN.register().catch(() => {})
          }
        }).catch(() => {})
      } catch {}

      const regListener = PN.addListener('registration', ({ value: token }) => {
        registerFCMToken(token)
      })

      const msgListener = PN.addListener('pushNotificationReceived', (notification) => {
        onNotification?.(notification)
      })

      const actionListener = PN.addListener('pushNotificationActionPerformed', (action) => {
        const data = action.notification?.data || {}
        if (data.type === 'order' && data.order_id) {
          window.location.pathname = `/orders/${data.order_id}`
        } else if (data.type === 'chat' && data.conversation_id) {
          window.location.pathname = `/chat/${data.conversation_id}`
        } else if (data.type === 'product' && data.product_id) {
          window.location.pathname = `/product/${data.product_id}`
        } else if (data.type === 'seller') {
          window.location.pathname = '/seller'
        } else if (data.url) {
          window.location.pathname = data.url
        }
      })

      removeListeners = async () => {
        try { (await regListener).remove() } catch {}
        try { (await msgListener).remove() } catch {}
        try { (await actionListener).remove() } catch {}
      }
    }).catch(() => {})

    return () => { removeListeners() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}


export async function clearPushBadge() {
  if (!isNative()) return
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    await PushNotifications.removeAllDeliveredNotifications()
  } catch {}
}
