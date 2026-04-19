/**
 * src/api/ai.js
 *
 * MICHA Express AI API client.
 * Connects frontend to the Django AI engine backend.
 * Replace all mock data calls with these functions.
 */
import client from './client'

// ── Onboarding Quiz ───────────────────────────────────────────────────────────

export const submitOnboardingQuiz = (quizData) =>
  client.post('/api/ai/onboarding-quiz/', quizData)

export const getQuizStatus = () =>
  client.get('/api/ai/onboarding-quiz/')

// ── Personalised Feed ─────────────────────────────────────────────────────────

export const getPersonalisedFeed = ({ limit = 20, offset = 0 } = {}) =>
  client.get('/api/ai/feed/', { params: { limit, offset } })

// ── Similar Products ──────────────────────────────────────────────────────────

export const getSimilarProducts = (productId, { limit = 10 } = {}) =>
  client.get(`/api/ai/similar/${productId}/`, { params: { limit } })

// ── Behavioral Tracking (fire and forget) ────────────────────────────────────

let _sessionId = null
const getSessionId = () => {
  if (!_sessionId) {
    _sessionId = `s_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }
  return _sessionId
}

export const trackEvent = async (eventType, data = {}) => {
  try {
    await client.post('/api/ai/event/', {
      event_type: eventType,
      session_id: getSessionId(),
      ...data,
    })
  } catch {
    // Fire-and-forget — never block UI on tracking failure
  }
}

// Convenience wrappers for common events
export const trackProductView = (product) =>
  trackEvent('view', {
    product_id: product.id,
    category: product.category,
    price: product.price,
    source: 'product_detail',
  })

export const trackDwell = (product, seconds) => {
  if (seconds >= 60) trackEvent('dwell_60', { product_id: product.id, category: product.category, dwell_seconds: seconds })
  else if (seconds >= 30) trackEvent('dwell_30', { product_id: product.id, category: product.category, dwell_seconds: seconds })
  else if (seconds >= 10) trackEvent('dwell_10', { product_id: product.id, category: product.category, dwell_seconds: seconds })
}

export const trackWishlistAdd = (product) =>
  trackEvent('wishlist_add', { product_id: product.id, category: product.category, price: product.price })

export const trackWishlistRemove = (product) =>
  trackEvent('wishlist_remove', { product_id: product.id, category: product.category })

export const trackCartAdd = (product) =>
  trackEvent('cart_add', { product_id: product.id, category: product.category, price: product.price })

export const trackCartRemove = (product) =>
  trackEvent('cart_remove', { product_id: product.id, category: product.category })

export const trackSearchClick = (productId, query) =>
  trackEvent('search_click', { product_id: productId, source: 'search', metadata: { query } })

export const trackRecommendationClick = (productId, source = 'home_feed') =>
  trackEvent('click_rec', { product_id: productId, source })

// ── Smart Search ──────────────────────────────────────────────────────────────

export const smartSearch = (query, { limit = 20 } = {}) =>
  client.get('/api/ai/search/', { params: { q: query, limit } })

// ── AI Chat ───────────────────────────────────────────────────────────────────

export const startAIChat = ({ productId, productName, language = 'pt' } = {}) =>
  client.post('/api/ai/chat/start/', {
    product_id: productId,
    product_name: productName,
    language,
  })

export const sendAIChatMessage = (conversationId, message) =>
  client.post(`/api/ai/chat/${conversationId}/`, { message })

export const getAIChatHistory = (conversationId) =>
  client.get(`/api/ai/chat/${conversationId}/`)

// ── Price Alerts ──────────────────────────────────────────────────────────────

export const watchPrice = (product, thresholdPct = 10) =>
  client.post('/api/ai/price-watch/', {
    product_id: product.id,
    price: product.price,
    product_name: product.name,
    threshold_pct: thresholdPct,
  })

export const unwatchPrice = (productId) =>
  client.delete(`/api/ai/price-watch/${productId}/`)

export const getPriceWatches = () =>
  client.get('/api/ai/price-watch/')

// ── Size Recommendations ──────────────────────────────────────────────────────

export const getSizeRecommendation = (productId, category) =>
  client.get('/api/ai/size/', { params: { product_id: productId, category } })

export const getSizeProfile = () =>
  client.get('/api/ai/size-profile/')

export const updateSizeProfile = (data) =>
  client.put('/api/ai/size-profile/', data)

// ── Taste Profile & Preferences ───────────────────────────────────────────────

export const getTasteProfile = () =>
  client.get('/api/ai/taste-profile/')

export const getNotificationPreferences = () =>
  client.get('/api/ai/notification-preferences/')

export const updateNotificationPreferences = (data) =>
  client.put('/api/ai/notification-preferences/', data)

// ── Content Generation (sellers only) ────────────────────────────────────────

export const generateProductDescription = (productData) =>
  client.post('/api/ai/content/generate-description/', productData)

export const translateProduct = (productData, targetLanguage) =>
  client.post('/api/ai/content/translate/', { ...productData, target_language: targetLanguage })

export const improveDescription = (description, category, language = 'pt') =>
  client.post('/api/ai/content/improve/', { description, category, language })

export const getReviewsSummary = (productId, language = 'pt') =>
  client.get(`/api/ai/content/reviews-summary/${productId}/`, { params: { language } })

// ── Trust Score ───────────────────────────────────────────────────────────────

export const getSellerTrustScore = (sellerId) =>
  client.get(`/api/trust/seller/${sellerId}/`)

export const getMyTrustScore = () =>
  client.get('/api/trust/me/')

export const getTrustLeaderboard = () =>
  client.get('/api/trust/leaderboard/')
