import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const CATEGORIES = ['Moda', 'Tecnologia', 'Casa & Jardim', 'Beleza', 'Alimentação', 'Desporto', 'Crianças', 'Arte & Artesanato', 'Outro']
const CONDITIONS = [{ value: 'new', label: 'Novo' }, { value: 'used', label: 'Usado' }, { value: 'refurbished', label: 'Recondicionado' }]

export default function SellerProductNewPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '', category: '', condition: 'new',
    price: '', original_price: '', stock: '',
    description: '', weight: '', express: false,
  })
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
    setError('')
  }

  const validate = () => {
    if (!form.name.trim()) return 'Insira o nome do produto.'
    if (!form.category) return 'Selecione uma categoria.'
    if (!form.price || isNaN(form.price)) return 'Insira um preço válido.'
    if (!form.stock || isNaN(form.stock)) return 'Insira o stock disponível.'
    if (!form.description.trim()) return 'Insira uma descrição.'
    return null
  }

  const handleSubmit = async () => {
    const err = validate()
    if (err) { setError(err); return }
    setLoading(true)
    // TODO: call sellerAPI.createProduct(form, images) when backend ready
    await new Promise(r => setTimeout(r, 1200))
    navigate('/seller', { state: { success: 'Produto adicionado com sucesso!' } })
  }

  const Label = ({ children, optional }) => (
    <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
      {children}{optional && <span style={{ color: '#555', fontWeight: 400 }}> (opcional)</span>}
    </label>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => navigate('/seller')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Novo produto</h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {error && (
            <div style={{ padding: '12px 16px', borderRadius: 12, background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#F87171' }}>
              {error}
            </div>
          )}

          {/* Image upload */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Label>Fotos do produto</Label>
            <div style={{ display: 'flex', gap: 10 }}>
              {/* Add photo button */}
              <div style={{
                width: 80, height: 80, borderRadius: 14,
                background: '#1E1E1E', border: '2px dashed #2A2A2A',
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', cursor: 'pointer', gap: 4, flexShrink: 0,
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: '#9A9A9A' }}>Adicionar</span>
              </div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.5, display: 'flex', alignItems: 'center' }}>
                Adicione até 8 fotos. A primeira será a foto principal.
              </p>
            </div>
          </div>

          {/* Product name */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Nome do produto</Label>
            <input className="input-base" name="name" placeholder="Ex: Vestido Capulana Premium"
              value={form.name} onChange={handleChange} />
          </div>

          {/* Category */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Label>Categoria</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {CATEGORIES.map(cat => (
                <button key={cat} onClick={() => setForm(f => ({ ...f, category: cat }))}
                  style={{
                    padding: '7px 14px', borderRadius: 50,
                    border: `1.5px solid ${form.category === cat ? '#C9A84C' : '#2A2A2A'}`,
                    background: form.category === cat ? 'rgba(201,168,76,0.1)' : 'transparent',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 12,
                    color: form.category === cat ? '#C9A84C' : '#9A9A9A', cursor: 'pointer',
                  }}>
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Condition */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Label>Estado</Label>
            <div style={{ display: 'flex', gap: 10 }}>
              {CONDITIONS.map(c => (
                <button key={c.value} onClick={() => setForm(f => ({ ...f, condition: c.value }))}
                  style={{
                    flex: 1, padding: '10px 0', borderRadius: 12, cursor: 'pointer',
                    border: `1.5px solid ${form.condition === c.value ? '#C9A84C' : '#2A2A2A'}`,
                    background: form.condition === c.value ? 'rgba(201,168,76,0.1)' : '#141414',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500,
                    color: form.condition === c.value ? '#C9A84C' : '#9A9A9A',
                  }}>
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* Price row */}
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label>Preço (Kz)</Label>
              <input className="input-base" name="price" type="number" placeholder="0"
                value={form.price} onChange={handleChange} />
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label optional>Preço original (Kz)</Label>
              <input className="input-base" name="original_price" type="number" placeholder="0"
                value={form.original_price} onChange={handleChange} />
            </div>
          </div>

          {/* Stock */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Stock disponível</Label>
            <input className="input-base" name="stock" type="number" placeholder="0"
              value={form.stock} onChange={handleChange} />
          </div>

          {/* Description */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Descrição</Label>
            <textarea className="input-base" name="description"
              placeholder="Descreva o produto em detalhe: materiais, tamanhos, cores disponíveis..."
              value={form.description} onChange={handleChange}
              rows={4} style={{ resize: 'none', lineHeight: 1.6 }} />
          </div>

          {/* Weight */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Peso (kg)</Label>
            <input className="input-base" name="weight" type="number" placeholder="0.5"
              value={form.weight} onChange={handleChange} />
          </div>

          {/* Express toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: '14px 16px' }}>
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500, color: '#FFFFFF' }}>Entrega Express</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>Entrega no mesmo dia em Luanda</p>
            </div>
            <div
              onClick={() => setForm(f => ({ ...f, express: !f.express }))}
              style={{
                width: 48, height: 26, borderRadius: 13,
                background: form.express ? '#C9A84C' : '#2A2A2A',
                position: 'relative', cursor: 'pointer',
                transition: 'background 0.2s ease', flexShrink: 0,
              }}>
              <div style={{
                position: 'absolute', top: 3,
                left: form.express ? 25 : 3,
                width: 20, height: 20, borderRadius: '50%',
                background: '#FFFFFF',
                transition: 'left 0.2s ease',
                boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
              }} />
            </div>
          </div>

          <button className="btn-primary" onClick={handleSubmit}
            disabled={loading} style={{ marginTop: 8, opacity: loading ? 0.7 : 1 }}>
            {loading ? 'A publicar...' : 'Publicar produto'}
          </button>
        </div>
      </div>
    </div>
  )
}
