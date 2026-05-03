/**
 * src/components/StoreSwitcher.jsx
 *
 * Multi-store switcher for seller dashboard.
 * Shows all stores, lets seller switch active store, create new store.
 * Sits at top of SellerLayout.
 */
import { useState, useEffect } from 'react'
import client from '@/api/client'

export default function StoreSwitcher({ onStoreChange }) {
  const [stores, setStores] = useState([])
  const [activeStoreId, setActiveStoreId] = useState(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newStoreName, setNewStoreName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => { loadStores() }, [])

  const loadStores = async () => {
    setLoading(true)
    try {
      const res = await client.get('/api/v1/stores/my-stores/')
      setStores(res.data.stores || [])
      setActiveStoreId(res.data.active_store_id)
      const active = res.data.stores?.find(s => s.id === res.data.active_store_id)
      if (active) onStoreChange?.(active)
    } catch {}
    setLoading(false)
  }

  const switchStore = async (storeId) => {
    try {
      await client.post(`/api/v1/stores/switch/${storeId}/`)
      setActiveStoreId(storeId)
      const store = stores.find(s => s.id === storeId)
      onStoreChange?.(store)
      setOpen(false)
    } catch {}
  }

  const createStore = async () => {
    if (!newStoreName.trim()) return
    setCreating(true)
    try {
      await client.post('/api/v1/stores/my-stores/', { name: newStoreName })
      setNewStoreName('')
      setShowCreate(false)
      loadStores()
    } catch (err) {
      alert(err.response?.data?.error || 'Erro ao criar loja.')
    } finally {
      setCreating(false)
    }
  }

  const activeStore = stores.find(s => s.id === activeStoreId)

  if (loading) return null

  return (
    <div style={{ position: 'relative', zIndex: 50 }}>
      {/* Trigger */}
      <button onClick={() => setOpen(v => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: 12, border: '1px solid #2A2A2A', background: '#1E1E1E', cursor: 'pointer', width: '100%' }}>
        {/* Store avatar */}
        <div style={{ width: 30, height: 30, borderRadius: 8, background: activeStore?.primary_color || '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          {activeStore?.logo
            ? <img src={activeStore.logo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 8 }} />
            : <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#0A0A0A' }}>
                {(activeStore?.name || 'L')[0].toUpperCase()}
              </span>
          }
        </div>

        <div style={{ flex: 1, textAlign: 'left' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF' }}>
            {activeStore?.name || 'Seleccionar loja'}
          </p>
          {stores.length > 1 && (
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>
              {stores.length} lojas • toque para mudar
            </p>
          )}
        </div>

        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 14, overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
          {(stores || []).map(store => (
            <button key={store.id} onClick={() => switchStore(store.id)}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', width: '100%', background: store.id === activeStoreId ? 'rgba(201,168,76,0.08)' : 'none', border: 'none', cursor: 'pointer', borderBottom: '1px solid #1E1E1E' }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: store.primary_color || '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#0A0A0A' }}>
                  {store.name[0].toUpperCase()}
                </span>
              </div>
              <div style={{ flex: 1, textAlign: 'left' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: store.id === activeStoreId ? 600 : 400, color: store.id === activeStoreId ? '#C9A84C' : '#FFFFFF' }}>
                  {store.name}
                </p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>
                  {store.stats?.total_products} produtos · {store.stats?.total_sales} vendas
                </p>
              </div>
              {store.id === activeStoreId && (
                <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                </div>
              )}
            </button>
          ))}

          {/* Create new store */}
          {showCreate ? (
            <div style={{ padding: '12px 16px', borderTop: '1px solid #1E1E1E' }}>
              <input value={newStoreName} onChange={e => setNewStoreName(e.target.value)}
                placeholder="Nome da nova loja"
                style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '10px 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box', marginBottom: 8 }} />
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setShowCreate(false)}
                  style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', cursor: 'pointer' }}>
                  Cancelar
                </button>
                <button onClick={createStore} disabled={!newStoreName.trim() || creating}
                  style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer', opacity: !newStoreName.trim() ? 0.4 : 1 }}>
                  {creating ? 'A criar...' : 'Criar'}
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setShowCreate(true)}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', width: '100%', background: 'none', border: 'none', cursor: 'pointer', borderTop: '1px solid #1E1E1E' }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: '#1E1E1E', border: '1.5px dashed #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
              </div>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Criar nova loja</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}
