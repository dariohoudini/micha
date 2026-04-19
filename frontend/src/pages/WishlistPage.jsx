import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BottomNav from '@/components/shared/BottomNav'
import ProductCard from '@/components/buyer/ProductCard'
import { MOCK_PRODUCTS } from '@/components/buyer/mockData'

export default function WishlistPage() {
  const navigate = useNavigate()
  // Mock wishlist with first 3 products — replace with API
  const [wishlist, setWishlist] = useState(MOCK_PRODUCTS.slice(0, 3))

  const removeFromWishlist = (id) => setWishlist(w => w.filter(p => p.id !== id))

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 16px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>
          Lista de desejos
        </h1>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{wishlist.length} produto(s)</span>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {wishlist.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 16, padding: '0 32px' }}>
            <div style={{ width: 72, height: 72, borderRadius: 18, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', textAlign: 'center' }}>Lista vazia</h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>Guarde produtos que gosta para os encontrar facilmente.</p>
            <button className="btn-primary" onClick={() => navigate('/home')} style={{ marginTop: 4 }}>Explorar produtos</button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '0 16px 20px' }}>
            {wishlist.map(product => (
              <ProductCard key={product.id} product={product} onPress={() => navigate(`/product/${product.id}`)} />
            ))}
          </div>
        )}
      </div>
      <BottomNav />
    </div>
  )
}
