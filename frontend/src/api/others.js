import client from './client'

export const notificationsAPI = {
  unreadCount: () => client.get('/api/v1/notifications/unread-count/'),
  getNotifications: (params = {}) => client.get('/api/v1/notifications/', { params }),
  markRead: (id) => client.post(`/api/v1/notifications/${id}/read/`),
  markAllRead: () => client.post('/api/v1/notifications/read-all/'),
}

export const storesAPI = {
  myStores: () => client.get('/api/v1/stores/my/'),
  createStore: (data) => client.post('/api/v1/stores/my/', data),
  switchStore: (storeId) => Promise.resolve({ data: { store_id: storeId } }), // handled client-side
  getSettings: (storeId) => client.get(`/api/v1/stores/${storeId}/`),
  updateSettings: (storeId, data) => client.patch(`/api/v1/stores/${storeId}/updangs/`, data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  getAnalytics: (storeId, period = 7) => client.get(`/api/v1/stores/${storeId}/analytics/`, { params: { period } }),
}

export const disputesAPI = {
  fileDispute: (data) => client.post('/api/v1/disputes/open/', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  myDisputes: () => client.get('/api/v1/disputes/my/'),
  respond: (id, data) => client.post(`/api/v1/disputes/${id}/message/`, data, { headers: { 'Content-Type': 'multipart/form-data' } }),
}
