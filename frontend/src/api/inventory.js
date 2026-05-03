import client from './client'

export const inventoryAPI = {
  // Stock
  getInventory: (params) => client.get('/api/v1/inventory/', { params }),
  updateStock: (productId, quantity) => client.patch(`/api/v1/inventory/${productId}/`, { quantity }),
  bulkUpdateStock: (items) => client.post('/api/v1/inventory/bulk-update/', { items }),

  // Low stock
  getLowStockAlerts: () => client.get('/api/v1/inventory/low-stock/'),
  setStockThreshold: (productId, threshold) => client.patch(`/api/v1/inventory/${productId}/threshold/`, { threshold }),

  // Reservations
  getReservations: () => client.get('/api/v1/inventory/reservations/'),
}

export default inventoryAPI
