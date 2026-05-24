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
      },

      logout: async () => {
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
        set({ user: null, isAuth: false, isSeller: false, isStaff: false })
      },

      updateUser: (updates) => {
        const updated = { ...get().user, ...updates }
        tokenStorage.setUser(updated)
        set({ user: updated, isSeller: updated.is_seller || false })
      },
    }),
    {
      name: 'micha-auth',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ user: state.user, isAuth: state.isAuth }),
    }
  )
)
