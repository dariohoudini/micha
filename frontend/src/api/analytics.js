import api from './client'

export const analyticsApi = {
  trackEvent: (event, productId = null, sessionId = '') =>
    api.post('/api/v1/analytics/track/', {
      event,
      product_id: productId,
      session_id: sessionId,
    }),

  getFunnel: (days = 30) =>
    api.get('/api/v1/analytics/funnel/', { params: { days } }),

  getSellerPerformance: () =>
    api.get('/api/v1/analytics/seller/performance/'),

  getGeoStats: () =>
    api.get('/api/v1/analytics/admin/geo/'),

  getRealTime: () =>
    api.get('/api/v1/analytics/admin/realtime/'),
}
