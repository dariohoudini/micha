import api from './client'

export const walletApi = {
  getWallet: () =>
    api.get('/api/v1/payments/wallet/'),

  getTransactions: (params = {}) =>
    api.get('/api/v1/payments/wallet/transactions/', { params }),

  getBankAccounts: () =>
    api.get('/api/v1/payments/bank-accounts/'),

  addBankAccount: (data) =>
    api.post('/api/v1/payments/bank-accounts/', data),

  updateBankAccount: (id, data) =>
    api.patch(`/api/v1/payments/bank-accounts/${id}/`, data),

  deleteBankAccount: (id) =>
    api.delete(`/api/v1/payments/bank-accounts/${id}/`),

  // Gap-Coverage CH16 — money-out needs a fresh second factor. A TOTP
  // code rides the X-TOTP-Code header (never the body); without one the
  // request relies on a live step-up window.
  requestPayout: (data) => {
    const { totp_code, ...body } = data || {}
    return api.post('/api/v1/payments/payout/request/', body,
      totp_code ? { headers: { 'X-TOTP-Code': totp_code } } : undefined)
  },

  // Open a 5-minute step-up window with a verified 2FA code.
  stepUp: (totpCode) =>
    api.post('/api/v1/auth/step-up/', { totp_code: totpCode }),

  adminGetPayouts: (params = {}) =>
    api.get('/api/v1/payments/payout/admin/', { params }),

  adminPayoutAction: (id, data) =>
    api.patch(`/api/v1/payments/payout/admin/${id}/`, data),
}
