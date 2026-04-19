import api from './client'

export const ordersAPI = {
  getCart: () =>
    api.get('/orders/cart/'),

  addToCart: (productId, quantity, variant) =>
    api.post('/orders/cart/add/', { product_id: productId, quantity, variant }),

  removeFromCart: (itemId) =>
    api.delete(`/orders/cart/items/${itemId}/`),

  checkout: (data) =>
    api.post('/orders/checkout/', data),

  getOrders: () =>
    api.get('/orders/'),

  getOrder: (id) =>
    api.get(`/orders/${id}/`),

  trackOrder: (id) =>
    api.get(`/orders/${id}/tracking/`),
}
