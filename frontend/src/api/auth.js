import api from './client'

export const authAPI = {
  register: (data) => api.post('/api/v1/auth/register/', data),
  login: (email, password) => api.post('/api/v1/auth/login/', { email, password }),
  verifyEmail: (email, otp) => api.post('/api/v1/auth/verify-email/', { email, otp }),
  resendOTP: (email) => api.post('/api/v1/auth/resend-email-otp/', { email }),
  forgotPassword: (email) => api.post('/api/v1/auth/forgot-password/', { email }),
  resetPassword: (email, otp, new_password) => api.post('/api/v1/auth/reset-password/', { email, otp, new_password }),
  logout: (refresh) => api.post('/api/v1/auth/logout/', { refresh }),
}

export const profileAPI = {
  getProfile: () => api.get('/api/v1/auth/profile/'),
  updateProfile: (data) => api.patch('/api/v1/auth/profile/update/', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  changePassword: (data) => api.post('/api/v1/auth/change-password/', data),
  changeEmail: (data) => api.post('/api/v1/auth/change-email/', data),
  changePhone: (data) => api.post('/api/v1/auth/change-phone/', data),
  deleteAccount: (data) => api.post('/api/v1/auth/delete-account/', data),
  cancelDeletion: () => api.post('/api/v1/auth/cancel-deletion/'),
  exportData: () => api.get('/api/v1/auth/data-export/'),
}

export const twoFAAPI = {
  setup: () => api.post('/api/v1/auth/2fa/setup/'),
  enable: (code) => api.post('/api/v1/auth/2fa/enable/', { code }),
  disable: (code) => api.post('/api/v1/auth/2fa/disable/', { code }),
}

export const loyaltyAPI = {
  getLoyalty: () => api.get('/api/v1/auth/loyalty/'),
  redeemPoints: (points) => api.post('/api/v1/auth/loyalty/redeem/', { points }),
  getReferral: () => api.get('/api/v1/auth/referral/'),
  claimReferral: (code) => api.post('/api/v1/auth/referral/', { code }),
}

export const sessionAPI = {
  getSessions: () => api.get('/api/v1/auth/sessions/'),
  revokeSession: (sessionId) => api.delete(`/api/v1/auth/sessions/${sessionId}/`),
}
