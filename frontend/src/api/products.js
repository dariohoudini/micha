import api from './client'

export const productsAPI = {
  getFeed: (cursor) =>
    api.get('/products/feed/', { params: { cursor } }),

  getProduct: (id) =>
    api.get(`/products/${id}/`),

  search: (query, filters) =>
    api.get('/products/search/', { params: { q: query, ...filters } }),

  getCategories: () =>
    api.get('/products/categories/'),
}
