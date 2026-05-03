// frontend/src/api/cart.js
import client from './client'

export const cartAPI = {
  getCart: () => client.get('/api/v1/cart/'),
  addToCart: (data) => client.post('/api/v1/cart/', data),
  updateCartItem: (id, data) => client.patch(`/api/v1/cart/items/${id}/`, data),
  removeFromCart: (id) => client.delete(`/api/v1/cart/items/${id}/`),
  clearCart: () => client.delete('/api/v1/cart/clear/'),
}
