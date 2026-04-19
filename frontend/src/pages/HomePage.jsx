import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import BottomNav from '@/components/shared/BottomNav'
import PromoBanner from '@/components/buyer/PromoBanner'
import CategoryPills from '@/components/buyer/CategoryPills'
import SearchBar from '@/components/buyer/SearchBar'
import ProductCard from '@/components/buyer/ProductCard'
import { MOCK_PRODUCTS } from '@/components/buyer/mockData'

export default function HomePage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const selectedCategory = useUIStore(s => s.selectedCategory)
  const setSelectedCategory = useUIStore(s => s.setSelectedCategory)

  const products = MOCK_PRODUCTS
  const expressProducts = products.filter(p => p.express).slice(0, 6)
  const filtered = selectedCategory === 'all'
    ? products
    : products.filter(p => p.category === selectedCategory)

  const firstName = user?.username || user?.email?.split('@')[0] || 'Cliente'

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: '#0A0A0A',
    }}>

      {/* Top bar */}
      <div style={{ padding: '52px 16px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 2 }}>
              Olá, {firstName} 👋
            </p>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
              O que procura hoje?
            </h1>
          </div>
          <button
            onClick={() => navigate('/notifications')}
            aria-label="Notificações"
            style={{
              width: 42, height: 42, borderRadius: 12,
              background: '#1E1E1E', border: '1px solid #2A2A2A',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', position: 'relative',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
              stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <div style={{
              position: 'absolute', top: 8, right: 8,
              width: 7, height: 7, borderRadius: '50%',
              background: '#C9A84C', border: '1.5px solid #0A0A0A',
            }} />
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingBottom: 20 }}>

          <SearchBar />
          <PromoBanner />
          <CategoryPills selected={selectedCategory} onSelect={setSelectedCategory} />

          {/* Express section */}
          {selectedCategory === 'all' && (
            <section>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0 16px', marginBottom: 12,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="#C9A84C">
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                  </svg>
                  <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#FFFFFF' }}>
                    Express
                  </h2>
                </div>
                <button
                  onClick={() => navigate('/explore', { state: { filter: 'express' } })}
                  style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  Ver todos →
                </button>
              </div>
              <div style={{
                display: 'flex', gap: 12,
                overflowX: 'auto', padding: '0 16px',
                scrollbarWidth: 'none',
              }}>
                {expressProducts.map(product => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    size="small"
                    onPress={() => navigate(`/product/${product.id}`)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Main grid */}
          <section>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '0 16px', marginBottom: 12,
            }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#FFFFFF' }}>
                Todos os Produtos
              </h2>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>
                {filtered.length} artigos
              </span>
            </div>
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr',
              gap: 12, padding: '0 16px',
            }}>
              {filtered.map(product => (
                <ProductCard
                  key={product.id}
                  product={product}
                  onPress={() => navigate(`/product/${product.id}`)}
                />
              ))}
            </div>
          </section>

        </div>
      </div>

      {/* Bottom nav — must be outside .screen, inside main wrapper */}
      <BottomNav />

    </div>
  )
}
