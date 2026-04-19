import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { tokenStorage } from '@/api/tokenStorage'

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
          set({ user, isAuth: true, isSeller: user.is_seller || false, isStaff: user.is_staff || false, loading: false })
        } else {
          set({ loading: false })
        }
      },

      login: (userData, tokens) => {
        tokenStorage.setAccessToken(tokens.access)
        tokenStorage.setRefreshToken(tokens.refresh)
        tokenStorage.setUser(userData)
        set({ user: userData, isAuth: true, isSeller: userData.is_seller || false, isStaff: userData.is_staff || false })
      },

      logout: async () => {
        try {
          const { default: api } = await import('@/api/client')
          await api.post('/auth/logout/', { refresh: tokenStorage.getRefreshToken() })
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
