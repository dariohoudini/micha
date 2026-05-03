import client from './client'

export const promotionsAPI = {
  // Coupons
  validateCoupon: (code) => client.post('/api/v1/promotions/coupons/validate/', { code }),

  // Flash sales
  getActiveFlashSales: () => client.get('/api/v1/promotions/flash-sales/'),
  createFlashSale: (data) => client.post('/api/v1/promotions/seller/flash-sales/', data),
  getMyFlashSales: () => client.get('/api/v1/promotions/seller/flash-sales/'),
  deleteFlashSale: (id) => client.delete(`/api/v1/promotions/seller/flash-sales/${id}/`),

  // Seller coupons
  getMyCoupons: () => client.get('/api/v1/promotions/seller/coupons/'),
  createCoupon: (data) => client.post('/api/v1/promotions/seller/coupons/', data),
}

export default promotionsAPI
