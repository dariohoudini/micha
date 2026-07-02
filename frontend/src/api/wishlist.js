// frontend/src/api/wishlist.js
import client from './client'

export const wishlistAPI = {
  getWishlist: () => client.get('/api/v1/wishlist/'),
  addToWishlist: (productId) => client.post('/api/v1/wishlist/add/', { product_id: productId }),
  removeFromWishlist: (id) => client.delete(`/api/v1/wishlist/items/${id}/`),
}
