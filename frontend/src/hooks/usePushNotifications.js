import { useEffect } from 'react'
import { Capacitor } from '@capacitor/core'
import client from '@/api/client'

const isNative = () => Capacitor.isNativePlatform()

async function registerFCMToken(token) {
  try {
    await client.post('/api/v1/notifications/push/register/', { token, platform: Capacitor.getPlatform() })
  } catch {}
}

export function usePushNotifications({ onNotification } = {}) {
  useEffect(() => {
    if (!isNative()) return

    let PushNotifications
    let removeListeners = () => {}

    import('@capacitor/push-notifications').then(({ PushNotifications: PN }) => {
      PushNotifications = PN

      PN.requestPermissions().then(({ receive }) => {
        if (receive === 'granted') {
          PN.register()
        }
      })

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
        ;(await regListener).remove()
        ;(await msgListener).remove()
        ;(await actionListener).remove()
      }
    })

    return () => { removeListeners() }
  }, [])
}

export async function clearPushBadge() {
  if (!isNative()) return
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    await PushNotifications.removeAllDeliveredNotifications()
  } catch {}
}
