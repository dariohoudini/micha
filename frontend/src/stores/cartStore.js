import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

/**
 * Cart store.
 *
 * Persistence
 * ───────────
 * Items live in localStorage so the cart survives page reloads,
 * tab closes, and crucially — offline sessions. The backend cart
 * (apps/cart) is the source of truth WHEN logged in; the local
 * store is the source of truth when anonymous OR when offline.
 *
 * Sync model (R5-B)
 * ─────────────────
 * The store does NOT make HTTP calls directly. ``lib/cartSync.js``
 * watches for online/auth events and pushes the local items to
 * ``/api/v1/cart/merge/`` — an idempotent endpoint that folds the
 * local cart into the server cart with stock clamping. After a
 * successful merge, the sync engine calls ``replaceItems()`` to
 * adopt the server's authoritative shape.
 *
 * syncStatus
 * ──────────
 *   'idle'    nothing pending, nothing in flight
 *   'syncing' merge call in flight
 *   'synced'  last merge succeeded (with lastSyncedAt timestamp)
 *   'offline' navigator.onLine is false — local-only writes
 *   'error'   last merge attempt failed; sync engine will retry
 */
export const useCartStore = create(
  persist(
    (set, get) => ({
      items: [],

      // R5-B: sync metadata, NOT persisted (computed at runtime).
      // Persisting these would lie to the user after a long offline
      // gap — better to recompute on each app start.
      syncStatus: 'idle',
      lastSyncedAt: null,
      lastError: '',

      get totalItems() { return get().items.reduce((s, i) => s + i.quantity, 0) },
      get totalPrice() { return get().items.reduce((s, i) => s + i.price * i.quantity, 0) },

      addItem: (product, quantity = 1) => {
        set((state) => {
          const exists = state.items.find(i => i.id === product.id)
          if (exists) {
            return { items: state.items.map(i => i.id === product.id ? { ...i, quantity: i.quantity + quantity } : i) }
          }
          const { quantity: _q, ...clean } = product
          return { items: [...state.items, { ...clean, quantity }] }
        })
      },

      incrementItem: (id) => set(state => ({
        items: state.items.map(i => i.id === id ? { ...i, quantity: i.quantity + 1 } : i)
      })),

      decrementItem: (id) => set(state => {
        const item = state.items.find(i => i.id === id)
        if (!item) return state
        if (item.quantity <= 1) return { items: state.items.filter(i => i.id !== id) }
        return { items: state.items.map(i => i.id === id ? { ...i, quantity: i.quantity - 1 } : i) }
      }),

      removeItem: (id) => set(state => ({ items: state.items.filter(i => i.id !== id) })),

      clearCart: () => set({ items: [] }),

      isInCart: (id) => get().items.some(i => i.id === id),

      getItem: (id) => get().items.find(i => i.id === id),

      // ── R5-B sync API ────────────────────────────────────────────
      //
      // setSyncStatus is called by lib/cartSync.js as a merge call
      // progresses. UI components can subscribe to ``syncStatus`` to
      // show a small badge ("syncing…", "offline", "synced 2m ago").
      setSyncStatus: (status, error = '') => set((state) => ({
        syncStatus: status,
        lastError: status === 'error' ? (error || state.lastError) : '',
        lastSyncedAt: status === 'synced' ? Date.now() : state.lastSyncedAt,
      })),

      // Replace the entire local items array. Called after a successful
      // /merge/ — the server returns the authoritative cart shape and
      // we adopt it so subsequent UI reads match the server. Maps the
      // server's item shape (product=pk, product_title, product_price,
      // product_image, quantity) into the local shape the UI expects.
      replaceItems: (serverItems) => set(() => ({
        items: (serverItems || []).map(it => ({
          // Use the server product pk as the local id — UI code keys
          // on `id` for "is in cart?" and increment/decrement lookups.
          id: it.product,
          cartItemId: it.id,
          title: it.product_title,
          price: Number(it.product_price) || 0,
          image: it.product_image,
          quantity: it.quantity,
          variantComboId: it.variant_combo || null,
        })),
      })),
    }),
    {
      name: 'micha-cart',
      storage: createJSONStorage(() => localStorage),
      // Only persist items — syncStatus / lastError are runtime-only.
      // If we persisted syncStatus the UI would lie ("synced 3d ago")
      // on first load before the engine has actually run.
      partialize: (state) => ({ items: state.items }),
    }
  )
)
