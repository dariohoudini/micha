import { useQuery, useMutation, useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { productsAPI } from '@/api/products'
import { ordersAPI } from '@/api/orders'
import { authAPI } from '@/api/auth'
import { toast } from '@/components/ui/Toast'

// ── Query Keys — centralized for cache invalidation ───────────────────────
export const QUERY_KEYS = {
  products: {
    all: ['products'],
    feed: (cursor) => ['products', 'feed', cursor],
    detail: (id) => ['products', id],
    search: (q, filters) => ['products', 'search', q, filters],
    categories: ['products', 'categories'],
  },
  orders: {
    all: ['orders'],
    detail: (id) => ['orders', id],
    tracking: (id) => ['orders', id, 'tracking'],
    cart: ['orders', 'cart'],
  },
  user: {
    profile: ['user', 'profile'],
    wishlist: ['user', 'wishlist'],
    notifications: ['user', 'notifications'],
  },
}

// ── Products ───────────────────────────────────────────────────────────────
export function useProductFeed() {
  return useInfiniteQuery({
    queryKey: QUERY_KEYS.products.feed(),
    queryFn: ({ pageParam }) => productsAPI.getFeed(pageParam),
    getNextPageParam: (lastPage) => lastPage.data?.next_cursor || undefined,
    select: (data) => ({
      pages: data.pages.flatMap(p => p.data?.results || []),
      pageParams: data.pageParams,
    }),
  })
}

export function useProduct(id) {
  return useQuery({
    queryKey: QUERY_KEYS.products.detail(id),
    queryFn: () => productsAPI.getProduct(id),
    select: (res) => res.data,
    enabled: !!id,
  })
}

export function useProductSearch(query, filters) {
  return useQuery({
    queryKey: QUERY_KEYS.products.search(query, filters),
    queryFn: () => productsAPI.search(query, filters),
    select: (res) => res.data?.results || [],
    enabled: !!query,
  })
}

export function useCategories() {
  return useQuery({
    queryKey: QUERY_KEYS.products.categories,
    queryFn: productsAPI.getCategories,
    select: (res) => res.data,
    staleTime: 1000 * 60 * 30, // Categories rarely change — cache 30 min
  })
}

// ── Orders ─────────────────────────────────────────────────────────────────
export function useOrders() {
  return useQuery({
    queryKey: QUERY_KEYS.orders.all,
    queryFn: ordersAPI.getOrders,
    select: (res) => res.data?.results || [],
  })
}

export function useOrder(id) {
  return useQuery({
    queryKey: QUERY_KEYS.orders.detail(id),
    queryFn: () => ordersAPI.getOrder(id),
    select: (res) => res.data,
    enabled: !!id,
  })
}

export function useCheckout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => ordersAPI.checkout(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.orders.all })
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || 'Erro ao processar pedido.')
    },
  })
}

// ── Auth ───────────────────────────────────────────────────────────────────
export function useRegister() {
  return useMutation({
    mutationFn: (data) => authAPI.register(data),
    onError: (err) => {
      const data = err.response?.data
      if (data?.field_errors) {
        const firstField = Object.keys(data.field_errors)[0]
        const msgs = data.field_errors[firstField]
        toast.error(Array.isArray(msgs) ? msgs[0] : msgs)
      }
    },
  })
}

export function useLogin() {
  return useMutation({
    mutationFn: ({ email, password }) => authAPI.login(email, password),
    onError: (err) => {
      toast.error(err.response?.data?.detail || 'Credenciais inválidas.')
    },
  })
}

// ── User profile ───────────────────────────────────────────────────────────
export function useProfile() {
  return useQuery({
    queryKey: QUERY_KEYS.user.profile,
    queryFn: authAPI.getProfile,
    select: (res) => res.data,
  })
}

export function useWishlist() {
  return useQuery({
    queryKey: QUERY_KEYS.user.wishlist,
    queryFn: () => import('@/api/client').then(m => m.default.get('/products/wishlist/')),
    select: (res) => res.data?.results || [],
  })
}

export function useNotifications() {
  return useQuery({
    queryKey: QUERY_KEYS.user.notifications,
    queryFn: () => import('@/api/client').then(m => m.default.get('/notifications/')),
    select: (res) => res.data?.results || [],
    refetchInterval: 1000 * 60, // Poll every 60 seconds
  })
}
