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

  requestPayout: (data) =>
    api.post('/api/v1/payments/payout/request/', data),

  adminGetPayouts: (params = {}) =>
    api.get('/api/v1/payments/payout/admin/', { params }),

  adminPayoutAction: (id, data) =>
    api.patch(`/api/v1/payments/payout/admin/${id}/`, data),
}
