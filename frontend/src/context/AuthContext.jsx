import { createContext, useContext, useState, useEffect } from 'react'
import { tokenStorage } from '@/api/tokenStorage'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Migrate any old localStorage tokens to secure storage
    tokenStorage.migrateFromLocalStorage()

    // Restore session from secure storage
    const savedUser = tokenStorage.getUser()
    const refreshToken = tokenStorage.getRefreshToken()

    if (savedUser && refreshToken) {
      setUser(savedUser)
    }
    setLoading(false)
  }, [])

  const login = (userData, tokens) => {
    // Store tokens securely
    tokenStorage.setAccessToken(tokens.access)
    tokenStorage.setRefreshToken(tokens.refresh)
    tokenStorage.setUser(userData)
    setUser(userData)
  }

  const logout = async () => {
    // Optionally call backend to blacklist token
    try {
      const { default: api } = await import('@/api/client')
      await api.post('/auth/logout/', {
        refresh: tokenStorage.getRefreshToken(),
      })
    } catch {
      // Ignore logout API errors — clear locally regardless
    }
    tokenStorage.clearAll()
    setUser(null)
  }

  const updateUser = (updates) => {
    const updated = { ...user, ...updates }
    tokenStorage.setUser(updated)
    setUser(updated)
  }

  return (
    <AuthContext.Provider value={{
      user, login, logout, updateUser,
      loading,
      isAuth: !!user,
      isSeller: user?.is_seller || false,
      isStaff: user?.is_staff || false,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
