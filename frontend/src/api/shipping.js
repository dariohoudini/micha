import api from './client'

export const shippingApi = {
  listAddresses: () =>
    api.get('/v1/shipping/addresses/'),

  createAddress: (data) =>
    api.post('/v1/shipping/addresses/', data),

  updateAddress: (id, data) =>
    api.patch(`/v1/shipping/addresses/${id}/`, data),

  deleteAddress: (id) =>
    api.delete(`/v1/shipping/addresses/${id}/`),

  setDefault: (id) =>
    api.post(`/v1/shipping/addresses/${id}/set-default/`),

  getZones: () =>
    api.get('/v1/shipping/zones/'),

  estimateCost: (data) =>
    api.post('/v1/shipping/estimate/', data),
}
