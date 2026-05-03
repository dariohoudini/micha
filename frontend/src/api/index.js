import { authAPI, profileAPI, twoFAAPI, loyaltyAPI, sessionAPI } from './auth'
import { cartAPI } from './cart'
import { wishlistAPI } from './wishlist'
import { promotionsAPI } from './promotions'
import { shippingAPI } from './shipping'
import { inventoryAPI } from './inventory'
import { reviewsAPI } from './reviews'
import { chatAPI } from './chat'
import { analyticsAPI } from './analytics'
import sellerAPI from './seller'
import { getNotifications, markRead, markAllRead, myStores, createStore, fileDispute, myDisputes, respond } from './others'

// Unified API object — import from here or directly from individual files
const API = {
  auth: authAPI,
  profile: profileAPI,
  twoFA: twoFAAPI,
  loyalty: loyaltyAPI,
  sessions: sessionAPI,
  cart: cartAPI,
  wishlist: wishlistAPI,
  seller: sellerAPI,
  promotions: promotionsAPI,
  shipping: shippingAPI,
  inventory: inventoryAPI,
  reviews: reviewsAPI,
  chat: chatAPI,
  analytics: analyticsAPI,
  notifications: { getNotifications, markRead, markAllRead },
  stores: { myStores, createStore },
  disputes: { fileDispute, myDisputes, respond },
}

export default API
