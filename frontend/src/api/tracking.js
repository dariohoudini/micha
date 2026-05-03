import client from './client'

/**
 * MICHA — Interaction Tracking
 * Feeds the recommendation engine with behavioural signals
 * Call these on every key user action
 */
export const trackInteraction = async (productId, interactionType, metadata = {}) => {
  try {
    await client.post('/api/v1/recommendations/track/', {
      product_id: productId,
      interaction_type: interactionType, // view, cart_add, wishlist, purchase, search_click, share
      metadata,
    })
  } catch {} // Never block UX for tracking
}

export const INTERACTION_TYPES = {
  VIEW: 'view',
  CART_ADD: 'cart_add',
  WISHLIST: 'wishlist',
  PURCHASE: 'purchase',
  SEARCH_CLICK: 'search_click',
  SHARE: 'share',
  REVIEW: 'review',
}

export default trackInteraction
