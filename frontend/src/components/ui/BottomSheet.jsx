import { useEffect, useRef, useState } from 'react'
import { useUIStore } from '@/stores/uiStore'

export default function BottomSheet() {
  const { sheet, closeSheet } = useUIStore()
  const [visible, setVisible] = useState(false)
  const [dragY, setDragY] = useState(0)
  const startY = useRef(0)
  const sheetRef = useRef(null)

  useEffect(() => {
    if (sheet) {
      setTimeout(() => setVisible(true), 10)
    } else {
      setVisible(false)
      setDragY(0)
    }
  }, [sheet])

  if (!sheet) return null

  const handleTouchStart = (e) => {
    startY.current = e.touches[0].clientY
  }

  const handleTouchMove = (e) => {
    const delta = e.touches[0].clientY - startY.current
    if (delta > 0) setDragY(delta)
  }

  const handleTouchEnd = () => {
    if (dragY > 120) {
      closeSheet()
    } else {
      setDragY(0)
    }
  }

  const Component = sheet.component

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={closeSheet}
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          opacity: visible ? 1 : 0,
          transition: 'opacity 0.3s ease',
        }}
      />

      {/* Sheet */}
      <div
        ref={sheetRef}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{
          position: 'fixed', bottom: 0, left: '50%',
          transform: `translateX(-50%) translateY(${visible ? dragY : '100%'}px)`,
          width: '100%', maxWidth: 430,
          background: '#141414',
          borderRadius: '24px 24px 0 0',
          border: '1px solid #2A2A2A',
          zIndex: 1001,
          transition: dragY > 0 ? 'none' : 'transform 0.4s cubic-bezier(0.32, 0.72, 0, 1)',
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
          maxHeight: '90vh',
          overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Handle */}
        <div style={{
          display: 'flex', justifyContent: 'center',
          padding: '12px 0 8px',
          flexShrink: 0,
        }}>
          <div style={{
            width: 36, height: 4, borderRadius: 2,
            background: '#2A2A2A',
          }} />
        </div>

        {/* Content */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          <Component {...sheet.props} onClose={closeSheet} />
        </div>
      </div>
    </>
  )
}
