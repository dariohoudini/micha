import { create } from 'zustand'

// Global UI state — modals, drawers, overlays
export const useUIStore = create((set) => ({
  // Bottom sheet
  bottomSheet: null,
  openBottomSheet: (content) => set({ bottomSheet: content }),
  closeBottomSheet: () => set({ bottomSheet: null }),

  // Search
  searchQuery: '',
  setSearchQuery: (q) => set({ searchQuery: q }),

  // Selected category on home
  selectedCategory: 'all',
  setSelectedCategory: (cat) => set({ selectedCategory: cat }),

  // Network
  isOnline: navigator.onLine,
  setOnline: (v) => set({ isOnline: v }),
}))
