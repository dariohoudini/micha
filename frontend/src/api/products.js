import api from './client'

export const productsAPI = {
  getFeed: (cursor) => api.get('/api/v1/recommendations/feed/', { params: { cursor } }),

  getProduct: (id) =>
    api.get(`/api/v1/products/${id}/`),

  search: (query, filters) =>
    api.get('/api/v1/products/', { params: { q: query, ...filters } }),

  getCategories: () =>
    api.get('/api/v1/products/categories/'),

  searchWithFilters: (params) => api.get('/api/v1/search/', { params: {
    q: params.query,
    category: params.category,
    min_price: params.minPrice,
    max_price: params.maxPrice,
    province: params.province,
    condition: params.condition,
    ordering: params.ordering,
    page: params.page,
    ...params
  }}),

  getPersonalisedFeed: (cursor) => api.get('/api/v1/recommendations/feed/', { params: { cursor } }),
  getSimilarProducts: (productId) => api.get(`/api/v1/recommendations/similar/${productId}/`),
  getTrending: () => api.get('/api/v1/search/trending/'),
  getSearchSuggestions: (q) => api.get('/api/v1/search/suggestions/', { params: { q } }),

  getProductGroups: (params) => api.get('/api/v1/products/groups/', { params }),
  getProductGroupOffers: (groupId) => api.get(`/api/v1/products/groups/${groupId}/offers/`),

  getProductQA: (productId) => api.get(`/api/v1/products/${productId}/qa/`),
  askQuestion: (productId, question) => api.post(`/api/v1/products/${productId}/qa/`, { question }),

  setPriceAlert: (slug) => api.post(`/api/v1/products/${slug}/price-alert/`),
  removePriceAlert: (slug) => api.delete(`/api/v1/products/${slug}/price-alert/`),
  checkPriceAlert: (slug) => api.get(`/api/v1/products/${slug}/price-alert/`),
}

export default productsAPI
