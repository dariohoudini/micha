import api from './client'

export const authAPI = {
  // POST { email, password, account_type }
  register: (data) =>
    api.post('/auth/register/', data),

  // POST { email, password } → { access, refresh }
  login: (email, password) =>
    api.post('/auth/login/', { email, password }),

  // POST { email, otp }
  verifyEmail: (email, otp) =>
    api.post('/auth/verify-email/', { email, otp }),

  // POST { email }
  resendOTP: (email) =>
    api.post('/auth/resend-otp/', { email }),

  // POST { email }
  forgotPassword: (email) =>
    api.post('/auth/forgot-password/', { email }),

  // POST { email, otp, new_password }
  resetPassword: (email, otp, new_password) =>
    api.post('/auth/reset-password/', { email, otp, new_password }),

  // POST { refresh }
  logout: () =>
    api.post('/auth/logout/', {
      refresh: localStorage.getItem('refresh_token'),
    }),
}
