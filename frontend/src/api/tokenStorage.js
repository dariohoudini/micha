/**
 * Secure Token Storage for MICHA Express
 *
 * Strategy:
 * - Access token: stored in memory only (not localStorage) — wiped on page refresh
 * - Refresh token: stored in sessionStorage (cleared when tab closes)
 * - User profile: stored in sessionStorage (non-sensitive display data only)
 *
 * Why not localStorage for tokens?
 * - localStorage is accessible to any JS on the page (XSS risk)
 * - sessionStorage is scoped to the tab and cleared on close
 * - Memory storage is the most secure but requires re-login on refresh
 *
 * Production upgrade path:
 * - Move to httpOnly cookies set by Django backend
 * - Backend sets: Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict
 * - Frontend never touches the refresh token directly
 */

// In-memory store — survives navigation but not page refresh
let _accessToken = null

export const tokenStorage = {
  // Access token — memory only
  setAccessToken(token) {
    _accessToken = token
  },

  getAccessToken() {
    return _accessToken
  },

  clearAccessToken() {
    _accessToken = null
  },

  // Refresh token — sessionStorage (tab-scoped)
  setRefreshToken(token) {
    try {
      sessionStorage.setItem('micha_rt', token)
    } catch {
      // sessionStorage unavailable (private mode etc)
      _accessToken = null
    }
  },

  getRefreshToken() {
    try {
      return sessionStorage.getItem('micha_rt')
    } catch {
      return null
    }
  },

  clearRefreshToken() {
    try {
      sessionStorage.removeItem('micha_rt')
    } catch {}
  },

  // User profile — sessionStorage (non-sensitive display data)
  setUser(user) {
    try {
      // Strip any sensitive fields before storing
      const safe = {
        id: user.id,
        email: user.email,
        username: user.username,
        is_seller: user.is_seller,
        is_staff: user.is_staff,
      }
      sessionStorage.setItem('micha_user', JSON.stringify(safe))
    } catch {}
  },

  getUser() {
    try {
      const raw = sessionStorage.getItem('micha_user')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },

  clearUser() {
    try {
      sessionStorage.removeItem('micha_user')
    } catch {}
  },

  // Clear everything
  clearAll() {
    _accessToken = null
    try {
      sessionStorage.removeItem('micha_rt')
      sessionStorage.removeItem('micha_user')
      // Also clear old localStorage tokens if they exist from previous version
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
    } catch {}
  },

  // Migrate old localStorage tokens on first load
  migrateFromLocalStorage() {
    try {
      const oldAccess = localStorage.getItem('access_token')
      const oldRefresh = localStorage.getItem('refresh_token')
      const oldUser = localStorage.getItem('user')

      if (oldAccess) {
        _accessToken = oldAccess
        localStorage.removeItem('access_token')
      }
      if (oldRefresh) {
        sessionStorage.setItem('micha_rt', oldRefresh)
        localStorage.removeItem('refresh_token')
      }
      if (oldUser) {
        sessionStorage.setItem('micha_user', oldUser)
        localStorage.removeItem('user')
      }
    } catch {}
  },
}
