import api from './client'

export const analyticsApi = {
  trackEvent: (event, productId = null, sessionId = '') =>
    api.post('/v1/analytics/track/', {
      event,
      product_id: productId,
      session_id: sessionId,
    }),

  getFunnel: (days = 30) =>
    api.get('/v1/analytics/funnel/', { params: { days } }),

  getSellerPerformance: () =>
    api.get('/v1/analytics/seller/performance/'),

  getGeoStats: () =>
    api.get('/v1/analytics/admin/geo/'),

  getRealTime: () =>
    api.get('/v1/analytics/admin/realtime/'),
}
