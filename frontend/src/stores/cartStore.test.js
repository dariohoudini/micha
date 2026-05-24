/**
 * cartStore unit tests (R1 Sprint 3).
 *
 * Plain Vitest unit tests against the Zustand store API. No DOM.
 *
 * To run:
 *   cd frontend && npm test
 *
 * Requires the operator dep install (see vitest.config.js comment).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useCartStore } from './cartStore'


function reset() {
  useCartStore.setState({ items: [], syncStatus: 'idle',
                          lastSyncedAt: null, lastError: '' })
}


describe('cartStore.addItem', () => {
  beforeEach(reset)

  it('adds a new product with given quantity', () => {
    useCartStore.getState().addItem({ id: 1, title: 'X', price: 100 }, 2)
    const items = useCartStore.getState().items
    expect(items).toHaveLength(1)
    expect(items[0].quantity).toBe(2)
  })

  it('increments quantity when product already in cart', () => {
    useCartStore.getState().addItem({ id: 1, title: 'X', price: 100 }, 1)
    useCartStore.getState().addItem({ id: 1, title: 'X', price: 100 }, 3)
    const items = useCartStore.getState().items
    expect(items).toHaveLength(1)
    expect(items[0].quantity).toBe(4)
  })
})


describe('cartStore.removeItem', () => {
  beforeEach(reset)

  it('removes only the matching product', () => {
    useCartStore.getState().addItem({ id: 1, title: 'A', price: 10 }, 1)
    useCartStore.getState().addItem({ id: 2, title: 'B', price: 20 }, 1)
    useCartStore.getState().removeItem(1)
    const items = useCartStore.getState().items
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe(2)
  })
})


describe('cartStore.replaceItems (sync adopt)', () => {
  beforeEach(reset)

  it('replaces local items with server shape', () => {
    useCartStore.getState().addItem({ id: 99, title: 'local', price: 1 }, 3)
    useCartStore.getState().replaceItems([
      { product: 1, id: 'srv-1', product_title: 'Server A',
        product_price: '100.00', quantity: 2 },
      { product: 2, id: 'srv-2', product_title: 'Server B',
        product_price: '50.00', quantity: 1 },
    ])
    const items = useCartStore.getState().items
    expect(items).toHaveLength(2)
    expect(items[0].id).toBe(1)               // mapped from server.product
    expect(items[0].cartItemId).toBe('srv-1')
    expect(items[0].price).toBe(100)          // coerced to Number
    expect(items.find(i => i.id === 99)).toBeUndefined()  // local cleared
  })
})


describe('cartStore.setSyncStatus', () => {
  beforeEach(reset)

  it("records lastSyncedAt only on 'synced'", () => {
    useCartStore.getState().setSyncStatus('syncing')
    expect(useCartStore.getState().lastSyncedAt).toBeNull()

    useCartStore.getState().setSyncStatus('synced')
    expect(useCartStore.getState().lastSyncedAt).toBeTypeOf('number')
  })

  it("records lastError only on 'error'", () => {
    useCartStore.getState().setSyncStatus('error', 'merge failed status=500')
    expect(useCartStore.getState().lastError).toContain('merge failed')

    // Transition off error clears the error.
    useCartStore.getState().setSyncStatus('idle')
    expect(useCartStore.getState().lastError).toBe('')
  })
})
