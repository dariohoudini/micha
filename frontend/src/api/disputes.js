import api from './client'

export const disputesApi = {
  open: (data) =>
    api.post('/api/v1/disputes/open/', data),

  list: () =>
    api.get('/api/v1/disputes/my/'),

  detail: (id) =>
    api.get(`/api/v1/disputes/${id}/`),

  sendMessage: (id, formData) =>
    api.post(`/api/v1/disputes/${id}/message/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  adminList: (params = {}) =>
    api.get('/api/v1/disputes/admin/', { params }),

  adminResolve: (id, data) =>
    api.patch(`/api/v1/disputes/admin/${id}/resolve/`, data),

  fraudFlags: () =>
    api.get('/api/v1/disputes/fraud/'),

  resolveFlag: (id) =>
    api.patch(`/api/v1/disputes/fraud/${id}/`),
}
