import client from './client'

export const ordersAPI = {
  // Checkout
  checkout: (data) => client.post('/api/v1/orders/checkout/', data),

  // Buyer orders
  getOrders: (params = {}) => client.get('/api/v1/orders/my/', { params }),
  getOrder: (id) => client.get(`/api/v1/orders/${id}/`),
  cancelOrder: (id, reason = '') => client.post(`/api/v1/orders/${id}/cancel/`, { reason }),
  confirmDelivery: (id) => client.post(`/api/v1/orders/${id}/confirm-delivery/`),
  requestRefund: (id, data) => client.post(`/api/v1/orders/${id}/refund/`, data),
  submitReturn: (id, data) => client.post(`/api/v1/orders/${id}/return/`, data),
  getReturn: (id) => client.get(`/api/v1/orders/${id}/return/`),
  getInvoice: (id) => client.get(`/api/v1/orders/${id}/invoice/`),
  trackOrder: (id) => client.get(`/api/v1/orders/${id}/`),

  // Seller orders
  getSellerOrders: (params = {}) => client.get('/api/v1/orders/seller/', { params }),
  updateOrderStatus: (id, status) => client.patch(`/api/v1/orders/${id}/status/`, { status }),
  addTracking: (id, trackingNumber, carrier = '') => client.patch(`/api/v1/orders/${id}/status/`, {
    tracking_number: trackingNumber,
    carrier,
  }),
  getPackingSlip: (id) => client.get(`/api/v1/orders/${id}/packing-slip/`),
}

export default ordersAPI
