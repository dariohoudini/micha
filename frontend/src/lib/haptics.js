/**
 * Haptic feedback utility
 * Uses Capacitor Haptics on native, Web Vibration API in browser
 */

let HapticsPlugin = null

async function loadHaptics() {
  if (HapticsPlugin) return HapticsPlugin
  try {
    if (window.Capacitor?.isNativePlatform?.()) {
      const { Haptics, ImpactStyle, NotificationType } = await import('@capacitor/haptics')
      HapticsPlugin = { Haptics, ImpactStyle, NotificationType }
    }
  } catch {}
  return HapticsPlugin
}

export const haptic = {
  // Light tap — for button presses, selections
  light: async () => {
    const h = await loadHaptics()
    if (h) {
      await h.Haptics.impact({ style: h.ImpactStyle.Light })
    } else if (navigator.vibrate) {
      navigator.vibrate(10)
    }
  },

  // Medium — for important actions (add to cart, submit)
  medium: async () => {
    const h = await loadHaptics()
    if (h) {
      await h.Haptics.impact({ style: h.ImpactStyle.Medium })
    } else if (navigator.vibrate) {
      navigator.vibrate(20)
    }
  },

  // Heavy — for confirmations, completions
  heavy: async () => {
    const h = await loadHaptics()
    if (h) {
      await h.Haptics.impact({ style: h.ImpactStyle.Heavy })
    } else if (navigator.vibrate) {
      navigator.vibrate([15, 10, 15])
    }
  },

  // Success — for order confirmed, payment success
  success: async () => {
    const h = await loadHaptics()
    if (h) {
      await h.Haptics.notification({ type: h.NotificationType.Success })
    } else if (navigator.vibrate) {
      navigator.vibrate([10, 50, 10, 50, 30])
    }
  },

  // Error — for failed actions
  error: async () => {
    const h = await loadHaptics()
    if (h) {
      await h.Haptics.notification({ type: h.NotificationType.Error })
    } else if (navigator.vibrate) {
      navigator.vibrate([30, 20, 30, 20, 30])
    }
  },

  // Warning
  warning: async () => {
    const h = await loadHaptics()
    if (h) {
      await h.Haptics.notification({ type: h.NotificationType.Warning })
    } else if (navigator.vibrate) {
      navigator.vibrate([20, 30, 20])
    }
  },
}
