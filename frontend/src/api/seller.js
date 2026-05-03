import api from './client'

export const sellerApi = {
  getDashboard: () =>
    api.get('/v1/seller/dashboard/'),

  getProfile: () =>
    api.get('/v1/seller/profile/'),

  updateProfile: (data) =>
    api.patch('/v1/seller/profile/', data),

  getFaqs: () =>
    api.get('/v1/seller/faq/'),

  createFaq: (data) =>
    api.post('/v1/seller/faq/', data),

  updateFaq: (id, data) =>
    api.patch(`/v1/seller/faq/${id}/`, data),

  deleteFaq: (id) =>
    api.delete(`/v1/seller/faq/${id}/`),

  getAnnouncements: () =>
    api.get('/v1/seller/announcements/'),

  toggleHoliday: (data) =>
    api.post('/v1/seller/holiday/', data),

  getOnboarding: () =>
    api.get('/v1/seller/onboarding/'),

  getOrders: (params = {}) =>
    api.get('/v1/orders/seller/', { params }),

  getInventory: (params = {}) =>
    api.get('/v1/inventory/', { params }),

  getPerformance: () =>
    api.get('/v1/analytics/seller/performance/'),
}
