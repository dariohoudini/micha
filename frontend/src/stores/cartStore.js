import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export const useCartStore = create(
  persist(
    (set, get) => ({
      items: [],

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
    }),
    {
      name: 'micha-cart',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
