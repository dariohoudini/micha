import { useState, useRef } from 'react'

export function useCartFly() {
  const [flying, setFlying] = useState(false)
  const [flyPos, setFlyPos] = useState({ x: 0, y: 0 })

  const triggerFly = (buttonRef) => {
    if (!buttonRef?.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const cartIcon = document.querySelector('[data-cart-icon]')
    if (!cartIcon) return
    const cartRect = cartIcon.getBoundingClientRect()
    setFlyPos({
      startX: rect.left + rect.width / 2,
      startY: rect.top + rect.height / 2,
      endX: cartRect.left + cartRect.width / 2,
      endY: cartRect.top + cartRect.height / 2,
    })
    setFlying(true)
    setTimeout(() => setFlying(false), 700)
  }

  return { flying, flyPos, triggerFly }
}

export function CartFlyParticle({ flying, flyPos }) {
  if (!flying) return null
  return (
    <div style={{
      position: 'fixed', zIndex: 9999, pointerEvents: 'none',
      width: 20, height: 20, borderRadius: '50%',
      background: '#C9A84C',
      left: flyPos.startX - 10,
      top: flyPos.startY - 10,
      animation: 'cartFly 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards',
    }}>
      <style>{`
        @keyframes cartFly {
          0% { transform: translate(0,0) scale(1); opacity: 1; }
          80% { transform: translate(${flyPos.endX - flyPos.startX}px, ${flyPos.endY - flyPos.startY}px) scale(0.3); opacity: 0.8; }
          100% { transform: translate(${flyPos.endX - flyPos.startX}px, ${flyPos.endY - flyPos.startY}px) scale(0); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
