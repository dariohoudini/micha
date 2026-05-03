import api from './client'

export const shippingApi = {
  listAddresses: () =>
    api.get('/api/v1/shipping/addresses/'),

  createAddress: (data) =>
    api.post('/api/v1/shipping/addresses/', data),

  updateAddress: (id, data) =>
    api.patch(`/api/v1/shipping/addresses/${id}/`, data),

  deleteAddress: (id) =>
    api.delete(`/api/v1/shipping/addresses/${id}/`),

  setDefault: (id) =>
    api.post(`/api/v1/shipping/addresses/${id}/set-default/`),

  getZones: () =>
    api.get('/api/v1/shipping/zones/'),

  estimateCost: (data) =>
    api.post('/api/v1/shipping/estimate/', data),
}
