import api from './client'

export const sellerApi = {
  getDashboard: () =>
    api.get('/api/v1/seller/dashboard/'),

  getProfile: () =>
    api.get('/api/v1/seller/profile/'),

  updateProfile: (data) =>
    api.patch('/api/v1/seller/profile/', data),

  getFaqs: () =>
    api.get('/api/v1/seller/faq/'),

  createFaq: (data) =>
    api.post('/api/v1/seller/faq/', data),

  updateFaq: (id, data) =>
    api.patch(`/api/v1/seller/faq/${id}/`, data),

  deleteFaq: (id) =>
    api.delete(`/api/v1/seller/faq/${id}/`),

  getAnnouncements: () =>
    api.get('/api/v1/seller/announcements/'),

  toggleHoliday: (data) =>
    api.post('/api/v1/seller/holiday/', data),

  getOnboarding: () =>
    api.get('/api/v1/seller/onboarding/'),

  getOrders: (params = {}) =>
    api.get('/api/v1/orders/seller/', { params }),

  getInventory: (params = {}) =>
    api.get('/api/v1/inventory/', { params }),

  getPerformance: () =>
    api.get('/api/v1/analytics/seller/performance/'),
}
