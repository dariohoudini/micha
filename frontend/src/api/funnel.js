import client from './client'

/**
 * Analytics funnel tracking
 * Call these on key user actions to track conversion funnel
 */
export const trackFunnel = async (eventType, data = {}) => {
  try {
    await client.post('/api/v1/analytics/funnel/', {
      event_type: eventType,
      ...data,
      timestamp: new Date().toISOString(),
    })
  } catch {} // Never block UX for analytics
}

export const FUNNEL_EVENTS = {
  VIEW_PRODUCT: 'view_product',
  ADD_TO_CART: 'add_to_cart',
  BEGIN_CHECKOUT: 'begin_checkout',
  PURCHASE: 'purchase',
  SEARCH: 'search',
  VIEW_CATEGORY: 'view_category',
  WISHLIST_ADD: 'wishlist_add',
  SHARE: 'share',
}

export default trackFunnel
