import { createContext, useContext, useState } from 'react'

const CartContext = createContext(null)

export function CartProvider({ children }) {
  const [items, setItems] = useState([])

  const totalItems = items.reduce((sum, i) => sum + i.quantity, 0)
  const totalPrice = items.reduce((sum, i) => sum + i.price * i.quantity, 0)

  // Add item or increase quantity if already in cart
  const addItem = (product, quantity = 1) => {
    setItems((prev) => {
      const exists = prev.find((i) => i.id === product.id)
      if (exists) {
        return prev.map((i) =>
          i.id === product.id
            ? { ...i, quantity: i.quantity + quantity }
            : i
        )
      }
      // Strip out any quantity field from product before storing
      const { quantity: _q, ...cleanProduct } = product
      return [...prev, { ...cleanProduct, quantity }]
    })
  }

  // Set exact quantity
  const setQuantity = (productId, quantity) => {
    if (quantity <= 0) {
      removeItem(productId)
      return
    }
    setItems((prev) =>
      prev.map((i) => i.id === productId ? { ...i, quantity } : i)
    )
  }

  // Increment / decrement
  const incrementItem = (productId) => {
    setItems((prev) =>
      prev.map((i) => i.id === productId ? { ...i, quantity: i.quantity + 1 } : i)
    )
  }

  const decrementItem = (productId) => {
    setItems((prev) => {
      const item = prev.find(i => i.id === productId)
      if (!item) return prev
      if (item.quantity <= 1) return prev.filter(i => i.id !== productId)
      return prev.map(i => i.id === productId ? { ...i, quantity: i.quantity - 1 } : i)
    })
  }

  const removeItem = (productId) => {
    setItems((prev) => prev.filter((i) => i.id !== productId))
  }

  const clearCart = () => setItems([])

  const isInCart = (productId) => items.some(i => i.id === productId)

  return (
    <CartContext.Provider value={{
      items, totalItems, totalPrice,
      addItem, setQuantity, incrementItem, decrementItem,
      removeItem, clearCart, isInCart,
    }}>
      {children}
    </CartContext.Provider>
  )
}

export const useCart = () => {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used inside CartProvider')
  return ctx
}
