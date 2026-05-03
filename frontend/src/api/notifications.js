import api from './client'

export const notificationsApi = {
  list: (params = {}) =>
    api.get('/api/v1/notifications/', { params }),

  unreadCount: () =>
    api.get('/api/v1/notifications/unread-count/'),

  markRead: (id) =>
    api.patch(`/api/v1/notifications/${id}/read/`),

  markAllRead: () =>
    api.patch('/api/v1/notifications/mark-all-read/'),
}
