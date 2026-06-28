import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/** ReturnRequestPage — User Process Flow §19.1 Return form. */
const S = { fontFamily: "'DM Sans', sans-serif" }
const input = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 14, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box' }
const label = { ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block' }

const REASONS = [
  { v: 'not_as_described', l: 'Item não corresponde à descrição' },
  { v: 'wrong_item', l: 'Item errado enviado' },
  { v: 'damaged', l: 'Item danificado / defeituoso' },
  { v: 'changed_mind', l: 'Mudei de ideia' },
  { v: 'never_arrived', l: 'Item não chegou' },
]
const METHODS = [
  { v: 'refund', l: 'Reembolso' },
  { v: 'exchange', l: 'Trocar por outro' },
  { v: 'partial', l: 'Reembolso parcial (fico com o item)' },
]

export default function ReturnRequestPage() {
  const navigate = useNavigate()
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [selectedItems, setSelectedItems] = useState({})
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [method, setMethod] = useState('refund')
  const [photos, setPhotos] = useState([])
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const photoRef = useRef()

  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 2500) }

  useEffect(() => {
    track('return.open', { order_id: orderId })
    client.get(`/api/v1/orders/${orderId}/`)
      .then(r => setOrder(r.data))
      .catch(() => show('Pedido não encontrado.', 'error'))
  }, [orderId])

  const onPick = (e) => {
    const files = Array.from(e.target.files || []).slice(0, 6 - photos.length)
    setPhotos(prev => [...prev, ...files.map(f => ({ file: f, url: URL.createObjectURL(f) }))])
    e.target.value = ''
  }

  const submit = async () => {
    const items = Object.keys(selectedItems).filter(k => selectedItems[k]).map(Number)
    if (!items.length) { show('Seleccione pelo menos um item.', 'error'); return }
    if (!reason) { show('Indique um motivo.', 'error'); return }
    if (['damaged', 'wrong_item'].includes(reason) && photos.length === 0) {
      show('Inclua pelo menos uma foto para este motivo.', 'error'); return
    }
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('order_id', orderId)
      fd.append('item_ids', JSON.stringify(items))
      fd.append('reason', reason)
      fd.append('description', description)
      fd.append('method', method)
      photos.forEach((p, i) => fd.append(`photo_${i}`, p.file, p.file.name))
      await client.post('/api/v1/disputes/returns/', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      track('return.submitted', { order_id: orderId, reason, method, item_count: items.length })
      show('Pedido de devolução enviado!')
      setTimeout(() => navigate(`/orders/${orderId}`), 1200)
    } catch (e) {
      show(e.response?.data?.detail || 'Erro ao enviar.', 'error')
    } finally { setBusy(false) }
  }

  const items = order?.items || []

  return (
    <BuyerLayout>
      {toast && <div style={{ position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13 }}>{toast.m}</div>}
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 12px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={{ width: 36, height: 36, borderRadius: 12, background: '#1E1E1E', border: 'none', cursor: 'pointer' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Devolução</h1>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 120px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {items.length > 0 && (
          <div>
            <label style={label}>Itens a devolver</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {items.map(it => (
                <label key={it.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, cursor: 'pointer' }}>
                  <input type="checkbox" checked={!!selectedItems[it.id]} onChange={e => setSelectedItems(p => ({ ...p, [it.id]: e.target.checked }))} />
                  <span style={{ ...S, fontSize: 13, color: '#FFF', flex: 1 }}>{it.product_title || it.title}</span>
                  <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>×{it.quantity || 1}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        <div>
          <label style={label}>Motivo *</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {REASONS.map(r => (
              <button key={r.v} onClick={() => setReason(r.v)} type="button"
                style={{ padding: '12px 14px', borderRadius: 10, border: `1.5px solid ${reason === r.v ? '#C9A84C' : '#2A2A2A'}`, background: reason === r.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 13, color: reason === r.v ? '#C9A84C' : '#FFF', cursor: 'pointer', textAlign: 'left' }}>{r.l}</button>
            ))}
          </div>
        </div>

        <div>
          <label style={label}>Descrição (opcional)</label>
          <textarea rows={3} maxLength={500} value={description} onChange={e => setDescription(e.target.value)}
            placeholder="Mais detalhes para o vendedor…" style={{ ...input, resize: 'vertical' }} />
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 4 }}>{description.length} / 500</p>
        </div>

        <div>
          <label style={label}>Fotos {['damaged', 'wrong_item'].includes(reason) ? '*' : '(opcional)'} </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {photos.map((p, i) => (
              <div key={i} style={{ position: 'relative', aspectRatio: '1', borderRadius: 10, overflow: 'hidden', background: '#1E1E1E' }}>
                <img src={p.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <button onClick={() => setPhotos(prev => prev.filter((_, j) => j !== i))}
                  style={{ position: 'absolute', top: 4, right: 4, width: 22, height: 22, borderRadius: '50%', background: 'rgba(0,0,0,0.7)', border: 'none', color: '#FFF', cursor: 'pointer', ...S, fontSize: 11 }}>✕</button>
              </div>
            ))}
            {photos.length < 6 && (
              <button onClick={() => photoRef.current?.click()}
                style={{ aspectRatio: '1', background: '#141414', border: '2px dashed #2A2A2A', borderRadius: 10, color: '#9A9A9A', cursor: 'pointer', ...S, fontSize: 22 }}>+</button>
            )}
          </div>
          <input ref={photoRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={onPick} />
        </div>

        <div>
          <label style={label}>Método</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {METHODS.map(m => (
              <button key={m.v} onClick={() => setMethod(m.v)} type="button"
                style={{ padding: '12px 14px', borderRadius: 10, border: `1.5px solid ${method === m.v ? '#C9A84C' : '#2A2A2A'}`, background: method === m.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 13, color: method === m.v ? '#C9A84C' : '#FFF', cursor: 'pointer', textAlign: 'left' }}>{m.l}</button>
            ))}
          </div>
        </div>
      </div>
      <div style={{ padding: '12px 16px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', borderTop: '1px solid #1A1A1A', background: '#0A0A0A' }}>
        <button onClick={submit} disabled={busy}
          style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: 'none', background: busy ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
          {busy ? 'A enviar…' : 'Submeter pedido de devolução'}
        </button>
      </div>
    </BuyerLayout>
  )
}
