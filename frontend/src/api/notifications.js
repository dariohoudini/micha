import api from './client'

export const notificationsApi = {
  list: (params = {}) =>
    api.get('/v1/notifications/', { params }),

  unreadCount: () =>
    api.get('/v1/notifications/unread-count/'),

  markRead: (id) =>
    api.patch(`/v1/notifications/${id}/read/`),

  markAllRead: () =>
    api.patch('/v1/notifications/mark-all-read/'),
}
