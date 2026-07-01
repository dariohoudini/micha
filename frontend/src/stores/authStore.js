import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { tokenStorage } from '@/api/tokenStorage'
import i18n from '@/i18n'

const syncLanguage = (user) => {
  const lang = user?.language
  if (lang && lang !== i18n.language) {
    i18n.changeLanguage(lang)
    try { localStorage.setItem('lang', lang) } catch {}
  }
}

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      isAuth: false,
      isSeller: false,
      isStaff: false,
      loading: true,

      init: () => {
        tokenStorage.migrateFromLocalStorage()
        const user = tokenStorage.getUser()
        const hasRefresh = !!tokenStorage.getRefreshToken()
        if (user && hasRefresh) {
          syncLanguage(user)
          set({ user, isAuth: true, isSeller: user.is_seller || false, isStaff: user.is_staff || false, loading: false })

          // Always re-hydrate the user from /auth/profile/ on app
          // boot. Reasons this is unconditional (not gated on a
          // "looks stale" check):
          //   1) Role flags (is_seller / is_staff / is_verified_seller)
          //      can be granted by an admin AFTER the user logged in
          //      — the persisted user object would never know.
          //   2) The previous "looksStale" gate only re-fetched when
          //      both flags were `undefined`. If a legacy persisted
          //      session had `is_seller: false` (instead of missing),
          //      we'd silently keep treating a real seller as a
          //      buyer. Unconditional refetch fixes that class of bug.
          //   3) Cost: one cheap authenticated GET per app launch.
          // We deliberately do NOT await it — UI renders immediately
          // with cached state, and the seller flag flips reactively
          // once the response lands.
          // NOTE: getProfile is exported from `profileAPI`, NOT from
          // `authAPI`. A prior version of this code destructured
          // `{ authAPI }` and called `authAPI.getProfile()` —
          // undefined function → silently rejected → seller flag
          // never refreshed → user stuck in buyer view. Keep this
          // import as `profileAPI`.
          import('@/api/auth')
            .then(({ profileAPI }) => profileAPI.getProfile())
            .then(res => {
              tokenStorage.setUser(res.data)
              set({
                user: res.data,
                isSeller: res.data.is_seller || false,
                isStaff: res.data.is_staff || false,
              })
            })
            .catch(() => {})
        } else {
          set({ loading: false })
        }
      },

      login: (userData, tokens) => {
        tokenStorage.setAccessToken(tokens.access)
        tokenStorage.setRefreshToken(tokens.refresh)
        tokenStorage.setUser(userData)
        syncLanguage(userData)
        set({ user: userData, isAuth: true, isSeller: userData.is_seller || false, isStaff: userData.is_staff || false })
        // User Process Flow §4.2 telemetry — log the auth event to DB.
        import('@/lib/userTrack').then(({ track }) => {
          track('auth.login', { user_id: userData.id, is_seller: !!userData.is_seller })
        }).catch(() => {})
        // R5-B: fire-and-forget cart sync. The effect in GlobalSetup
        // also reacts to isAuth changes, but triggering here gives a
        // crisper sync moment for the user who just logged in with
        // items in their anon cart. Dynamic import so the cart-sync
        // module isn't pulled into the auth-store chunk.
        import('@/lib/cartSync')
          .then(m => m.triggerCartSync())
          .catch(() => {})
      },

      logout: async () => {
        // User Process Flow §11.6 telemetry — log auth-end synchronously
        // so the event ships before tokens get cleared.
        try {
          const { track } = await import('@/lib/userTrack')
          track('auth.logout', {})
        } catch {}
        try {
          const { default: api } = await import('@/api/client')
          // R5: deactivate this device's push token BEFORE the auth
          // call. If we did it after the auth refresh-token is
          // invalidated, the unregister call would 401 and the device
          // would keep receiving pushes intended for the next user
          // who logs in here. Empty body = deactivate all tokens for
          // the calling user.
          try {
            await api.post('/api/v1/notifications/push/unregister/', {})
          } catch {}
          await api.post('/api/v1/auth/logout/', { refresh: tokenStorage.getRefreshToken() })
        } catch {}
        tokenStorage.clearAll()
        // Clear per-device flags that should NOT survive into the next
        // user's session on the same device. Pre-fix: a user who denied
        // push on this device would never let user-B get re-prompted
        // because the flag was permanently sticky.
        try {
          localStorage.removeItem('micha-push-asked-v1')
          // Cookie consent IS scoped per-key — keep it; it represents
          // the device user's choice and the next sign-in carries it.
        } catch {}
        set({ user: null, isAuth: false, isSeller: false, isStaff: false })
        // §34.4 — Navigation Stack Reset on sign-out. Broadcast a
        // window event so the root layout / SessionGuard can do a
        // `navigate("/login", { replace: true })` from within router
        // context. We can't call useNavigate() here (we're outside
        // React render) so an event listener bridges that gap.
        try {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('micha:auth-stack-reset', {
              detail: { reason: 'signout', to: '/login' },
            }))
          }
        } catch {}
      },

      updateUser: (updates) => {
        const updated = { ...get().user, ...updates }
        tokenStorage.setUser(updated)
        // Must also refresh isStaff — login awaits getProfile() then reads
        // isStaff from the store to route admins to /admin. Without this it
        // stayed false and staff landed on the buyer home.
        set({ user: updated, isSeller: updated.is_seller || false, isStaff: updated.is_staff || false })
      },
    }),
    {
      name: 'micha-auth',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ user: state.user, isAuth: state.isAuth }),
    }
  )
)
