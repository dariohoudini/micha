import { useQuery, useMutation, useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { productsAPI } from '@/api/products'
import { ordersAPI } from '@/api/orders'
import { authAPI } from '@/api/auth'
import { notificationsApi } from '@/api/notifications'
import { walletApi } from '@/api/wallet'
import { sellerApi } from '@/api/seller'
import { disputesApi } from '@/api/disputes'
import { shippingApi } from '@/api/shipping'
import { toast } from '@/components/ui/Toast'
import { parseApiError } from '@/hooks/useApiError'

// ── Query Keys ─────────────────────────────────────────────────────────────
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
    unreadCount: ['user', 'notifications', 'unread'],
  },
  wallet: {
    detail: ['wallet'],
    transactions: (page) => ['wallet', 'transactions', page],
    bankAccounts: ['wallet', 'bank-accounts'],
    payouts: ['wallet', 'payouts'],
  },
  seller: {
    dashboard: ['seller', 'dashboard'],
    orders: (params) => ['seller', 'orders', params],
    performance: ['seller', 'performance'],
    inventory: ['seller', 'inventory'],
  },
  disputes: {
    list: ['disputes'],
    detail: (id) => ['disputes', id],
  },
  shipping: {
    addresses: ['shipping', 'addresses'],
    zones: ['shipping', 'zones'],
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
    queryFn: notificationsApi.list,
    select: (res) => res.data?.results || [],
    refetchInterval: 60_000,
  })
}

export function useUnreadCount() {
  return useQuery({
    queryKey: QUERY_KEYS.user.unreadCount,
    queryFn: notificationsApi.unreadCount,
    select: (res) => res.data?.count ?? 0,
    refetchInterval: 30_000,
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: notificationsApi.markRead,
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: QUERY_KEYS.user.notifications })
      const prev = qc.getQueryData(QUERY_KEYS.user.notifications)
      qc.setQueryData(QUERY_KEYS.user.notifications, (old) => {
        if (!old?.data?.results) return old
        return {
          ...old,
          data: {
            ...old.data,
            results: old.data.results.map(n =>
              n.id === id ? { ...n, is_read: true } : n
            ),
          },
        }
      })
      return { prev }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(QUERY_KEYS.user.notifications, ctx.prev)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.user.notifications })
      qc.invalidateQueries({ queryKey: QUERY_KEYS.user.unreadCount })
    },
  })
}

export function useMarkAllRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.user.notifications })
      qc.invalidateQueries({ queryKey: QUERY_KEYS.user.unreadCount })
    },
  })
}

// ── Profile mutation ───────────────────────────────────────────────────────
export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => authAPI.updateProfile(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.user.profile })
      toast.success('Perfil actualizado com sucesso.')
    },
    onError: (err) => {
      toast.error(parseApiError(err))
    },
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (data) => authAPI.changePassword(data),
    onSuccess: () => toast.success('Senha alterada com sucesso.'),
    onError: (err) => toast.error(parseApiError(err)),
  })
}

// ── Wallet ─────────────────────────────────────────────────────────────────
export function useWallet() {
  return useQuery({
    queryKey: QUERY_KEYS.wallet.detail,
    queryFn: walletApi.getWallet,
    select: (res) => res.data,
  })
}

export function useWalletTransactions(page = 1) {
  return useQuery({
    queryKey: QUERY_KEYS.wallet.transactions(page),
    queryFn: () => walletApi.getTransactions({ page }),
    select: (res) => res.data,
  })
}

export function useBankAccounts() {
  return useQuery({
    queryKey: QUERY_KEYS.wallet.bankAccounts,
    queryFn: walletApi.getBankAccounts,
    select: (res) => res.data?.results || [],
  })
}

export function useRequestPayout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: walletApi.requestPayout,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.wallet.detail })
      qc.invalidateQueries({ queryKey: QUERY_KEYS.wallet.payouts })
      toast.success('Pedido de levantamento enviado.')
    },
    onError: (err) => toast.error(parseApiError(err)),
  })
}

// ── Seller ─────────────────────────────────────────────────────────────────
export function useSellerDashboard() {
  return useQuery({
    queryKey: QUERY_KEYS.seller.dashboard,
    queryFn: sellerApi.getDashboard,
    select: (res) => res.data,
  })
}

export function useSellerOrders(params) {
  return useQuery({
    queryKey: QUERY_KEYS.seller.orders(params),
    queryFn: () => sellerApi.getOrders(params),
    select: (res) => res.data,
  })
}

export function useSellerPerformance() {
  return useQuery({
    queryKey: QUERY_KEYS.seller.performance,
    queryFn: sellerApi.getPerformance,
    select: (res) => res.data,
    staleTime: 5 * 60_000,
  })
}

export function useSellerInventory() {
  return useQuery({
    queryKey: QUERY_KEYS.seller.inventory,
    queryFn: sellerApi.getInventory,
    select: (res) => res.data?.results || [],
  })
}

// ── Disputes ───────────────────────────────────────────────────────────────
export function useDisputes() {
  return useQuery({
    queryKey: QUERY_KEYS.disputes.list,
    queryFn: disputesApi.list,
    select: (res) => res.data?.results || [],
  })
}

export function useOpenDispute() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: disputesApi.open,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.disputes.list })
      toast.success('Disputa aberta com sucesso.')
    },
    onError: (err) => toast.error(parseApiError(err)),
  })
}

// ── Shipping ───────────────────────────────────────────────────────────────
export function useShippingAddresses() {
  return useQuery({
    queryKey: QUERY_KEYS.shipping.addresses,
    queryFn: shippingApi.listAddresses,
    select: (res) => res.data?.results || [],
  })
}

export function useSaveAddress() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => data.id
      ? shippingApi.updateAddress(data.id, data)
      : shippingApi.createAddress(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.shipping.addresses })
      toast.success('Endereço guardado.')
    },
    onError: (err) => toast.error(parseApiError(err)),
  })
}

export function useDeleteAddress() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: shippingApi.deleteAddress,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.shipping.addresses })
      toast.success('Endereço removido.')
    },
    onError: (err) => toast.error(parseApiError(err)),
  })
}
