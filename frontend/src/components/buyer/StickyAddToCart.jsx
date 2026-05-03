import { useState, useEffect } from 'react'
import { haptic } from '@/hooks/useUX'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'

export default function StickyAddToCart({ product, onAdd, loading }) {
  const [visible, setVisible] = useState(false)
  const [added, setAdded] = useState(false)

  useEffect(() => {
    const handler = () => setVisible(window.scrollY > 300)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])

  const handleAdd = async () => {
    haptic.success()
    await onAdd?.()
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  if (!visible) return null

  return (
    <div style={{
      position: 'fixed', bottom: 72, left: 0, right: 0, zIndex: 100,
      padding: '10px 16px',
      background: 'linear-gradient(to top, #0A0A0A 80%, transparent)',
      display: 'flex', gap: 10,
      transform: visible ? 'translateY(0)' : 'translateY(100%)',
      transition: 'transform 0.3s ease',
    }}>
      <div style={{ flex: 1, background: '#1E1E1E', borderRadius: 14, padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140 }}>{product?.title}</span>
        <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 15, fontWeight: 700, color: GOLD }}>{Number(product?.price).toLocaleString()} Kz</span>
      </div>
      <button onClick={handleAdd} disabled={loading} style={{
        padding: '12px 20px', borderRadius: 14, border: 'none', cursor: 'pointer',
        background: added ? '#059669' : GOLD, color: added ? '#fff' : '#000',
        fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700,
        transition: 'all 0.2s', flexShrink: 0, whiteSpace: 'nowrap',
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        {loading ? (
          <div style={{ width: 14, height: 14, border: '2px solid rgba(0,0,0,0.3)', borderTopColor: '#000', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
        ) : added ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        )}
        {added ? 'Adicionado' : 'Adicionar'}
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </button>
    </div>
  )
}
