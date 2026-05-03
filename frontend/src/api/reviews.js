import client from './client'

export const reviewsAPI = {
  // Product reviews
  getProductReviews: (productId, params = {}) => client.get(`/api/v1/reviews/product/${productId}/`, { params }),
  createProductReview: (data) => client.post('/api/v1/reviews/product/', data, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  getProductRating: (productId) => client.get(`/api/v1/reviews/product/${productId}/rating/`),
  flagReview: (reviewId, reason) => client.post(`/api/v1/reviews/product/${reviewId}/flag/`, { reason }),
  voteHelpful: (reviewId) => client.post(`/api/v1/reviews/${reviewId}/helpful/`),

  // Seller reviews
  getSellerReviews: (sellerId, params = {}) => client.get(`/api/v1/reviews/seller/${sellerId}/`, { params }),
  createSellerReview: (data) => client.post('/api/v1/reviews/create/', data),
  getSellerRating: (sellerId) => client.get(`/api/v1/reviews/seller/${sellerId}/rating/`),
  replyToReview: (reviewId, reply) => client.post(`/api/v1/reviews/${reviewId}/reply/`, { reply }),
}

export default reviewsAPI
