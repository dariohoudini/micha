import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'

const CATEGORIES = ['Moda', 'Tecnologia', 'Casa & Jardim', 'Beleza', 'Alimentação', 'Desporto', 'Crianças', 'Arte & Artesanato', 'Acessórios', 'Outro']
const CONDITIONS = [{ value: 'new', label: 'Novo' }, { value: 'used', label: 'Usado' }, { value: 'refurbished', label: 'Recondicionado' }]
const PROCESSING_TIMES = ['Mesmo dia', '1-2 dias úteis', '2-3 dias úteis', '3-5 dias úteis', '5-7 dias úteis']

export default function SellerProductNewPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const [form, setForm] = useState({
    name: '', category: '', condition: 'new',
    price: '', original_price: '', stock: '', sku: '',
    description: '', tags: '',
    has_variants: false, variants_text: '',
    express: false, free_shipping: false,
    weight: '', processing_time: '1-2 dias úteis',
  })

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
    setErrors(e => ({ ...e, [name]: null }))
  }

  const validate = (s) => {
    const errs = {}
    if (s === 1) {
      if (!form.name.trim()) errs.name = 'Insira o nome do produto'
      if (form.name.length > 100) errs.name = 'Máximo 100 caracteres'
      if (!form.category) errs.category = 'Selecione uma categoria'
      if (!form.price || isNaN(form.price) || Number(form.price) <= 0) errs.price = 'Insira um preço válido'
      if (form.original_price && Number(form.original_price) <= Number(form.price)) errs.original_price = 'Preço original deve ser maior que o preço de venda'
      if (!form.stock || isNaN(form.stock) || Number(form.stock) < 0) errs.stock = 'Insira o stock disponível'
    }
    if (s === 2) {
      if (!form.description.trim() || form.description.length < 10) errs.description = 'Descrição muito curta (mínimo 10 caracteres)'
      if (form.description.length > 2000) errs.description = 'Máximo 2000 caracteres'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleNext = () => { if (validate(step)) setStep(s => s + 1) }

  const handleSubmit = async () => {
    setLoading(true)
    await new Promise(r => setTimeout(r, 1200))
    showToast('Produto publicado com sucesso!')
    setTimeout(() => navigate('/seller/products'), 1500)
  }

  const Toggle = ({ name, label, sub }) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: '14px 16px' }}>
      <div>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500, color: '#FFFFFF' }}>{label}</p>
        {sub && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{sub}</p>}
      </div>
      <div onClick={() => setForm(f => ({ ...f, [name]: !f[name] }))}
        style={{ width: 44, height: 24, borderRadius: 12, background: form[name] ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0 }}>
        <div style={{ position: 'absolute', top: 3, left: form[name] ? 23 : 3, width: 18, height: 18, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }} />
      </div>
    </div>
  )

  const Field = ({ name, label, optional, error, children }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: error ? '#F87171' : '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        {label}{optional && <span style={{ color: '#555', fontWeight: 400 }}> (opcional)</span>}
      </label>
      {children}
      {error && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{error}</p>}
    </div>
  )

  const discount = form.price && form.original_price && Number(form.original_price) > Number(form.price)
    ? Math.round((1 - Number(form.price) / Number(form.original_price)) * 100)
    : null

  return (
    <SellerLayout title={step === 3 ? 'Pré-visualização' : 'Novo Produto'}>
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      {/* Step indicator */}
      <div style={{ padding: '8px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 16 }}>
          {['Informações', 'Descrição', 'Entrega'].map((s, i) => (
            <div key={s} style={{ display: 'flex', alignItems: 'center', flex: i < 2 ? 1 : 'none' }}>
              <button onClick={() => i + 1 < step && setStep(i + 1)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: i + 1 < step ? 'pointer' : 'default', padding: 0 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, background: step > i + 1 ? '#059669' : step === i + 1 ? '#C9A84C' : '#2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background 0.3s' }}>
                  {step > i + 1
                    ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                    : <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 700, color: step === i + 1 ? '#0A0A0A' : '#9A9A9A' }}>{i + 1}</span>
                  }
                </div>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: step === i + 1 ? '#C9A84C' : step > i + 1 ? '#059669' : '#9A9A9A' }}>{s}</span>
              </button>
              {i < 2 && <div style={{ flex: 1, height: 1, background: step > i + 1 ? '#059669' : '#2A2A2A', margin: '0 8px', transition: 'background 0.3s' }} />}
            </div>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Step 1 */}
          {step === 1 && <>
            {/* Image placeholders */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Fotos do produto
              </label>
              <div style={{ display: 'flex', gap: 10 }}>
                {[0, 1, 2, 3].map(i => (
                  <div key={i} style={{ width: 72, height: 72, borderRadius: 12, background: '#1E1E1E', border: i === 0 ? '2px dashed #C9A84C' : '2px dashed #2A2A2A', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0, gap: 4 }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={i === 0 ? '#C9A84C' : '#2A2A2A'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
                    {i === 0 && <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 8, color: '#C9A84C' }}>Principal</span>}
                  </div>
                ))}
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', lineHeight: 1.5, display: 'flex', alignItems: 'center' }}>Toque para adicionar. Primeira foto = imagem principal.</p>
              </div>
            </div>

            <Field name="name" label="Nome do produto" error={errors.name}>
              <input className="input-base" name="name" placeholder="Ex: Vestido Capulana Premium Tamanho M" value={form.name} onChange={handleChange} style={{ borderColor: errors.name ? 'rgba(220,38,38,0.5)' : undefined }} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: form.name.length > 90 ? '#f59e0b' : '#9A9A9A' }}>{form.name.length}/100</span>
            </Field>

            <Field name="category" label="Categoria" error={errors.category}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {CATEGORIES.map(cat => (
                  <button key={cat} type="button" onClick={() => { setForm(f => ({ ...f, category: cat })); setErrors(e => ({ ...e, category: null })) }}
                    style={{ padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${form.category === cat ? '#C9A84C' : errors.category ? 'rgba(220,38,38,0.3)' : '#2A2A2A'}`, background: form.category === cat ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: form.category === cat ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                    {cat}
                  </button>
                ))}
              </div>
            </Field>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Estado</label>
              <div style={{ display: 'flex', gap: 10 }}>
                {CONDITIONS.map(c => (
                  <button key={c.value} type="button" onClick={() => setForm(f => ({ ...f, condition: c.value }))}
                    style={{ flex: 1, padding: '10px 0', borderRadius: 12, cursor: 'pointer', border: `1.5px solid ${form.condition === c.value ? '#C9A84C' : '#2A2A2A'}`, background: form.condition === c.value ? 'rgba(201,168,76,0.1)' : '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: form.condition === c.value ? '#C9A84C' : '#9A9A9A' }}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <Field name="price" label="Preço (Kz)" error={errors.price}>
                <input className="input-base" name="price" type="number" inputMode="numeric" placeholder="0" value={form.price} onChange={handleChange} style={{ borderColor: errors.price ? 'rgba(220,38,38,0.5)' : undefined }} />
              </Field>
              <Field name="original_price" label="Preço original" optional error={errors.original_price}>
                <input className="input-base" name="original_price" type="number" inputMode="numeric" placeholder="0" value={form.original_price} onChange={handleChange} style={{ borderColor: errors.original_price ? 'rgba(220,38,38,0.5)' : undefined }} />
              </Field>
            </div>

            {discount && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 10, padding: '10px 14px' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#059669' }}>Desconto de {discount}% será exibido aos compradores</span>
              </div>
            )}

            <div style={{ display: 'flex', gap: 12 }}>
              <Field name="stock" label="Stock" error={errors.stock}>
                <input className="input-base" name="stock" type="number" inputMode="numeric" placeholder="0" value={form.stock} onChange={handleChange} style={{ borderColor: errors.stock ? 'rgba(220,38,38,0.5)' : undefined }} />
              </Field>
              <Field name="sku" label="SKU" optional>
                <input className="input-base" name="sku" placeholder="SKU-001" value={form.sku} onChange={handleChange} />
              </Field>
            </div>
          </>}

          {/* Step 2 */}
          {step === 2 && <>
            <Field name="description" label="Descrição detalhada" error={errors.description}>
              <textarea className="input-base" name="description"
                placeholder="Descreva o produto em detalhe: materiais, tamanhos, cores, cuidados, origem..."
                value={form.description} onChange={handleChange}
                rows={6} style={{ resize: 'none', lineHeight: 1.6, borderColor: errors.description ? 'rgba(220,38,38,0.5)' : undefined }} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: form.description.length > 1800 ? '#f59e0b' : '#9A9A9A' }}>{form.description.length}/2000</span>
            </Field>

            <Field name="tags" label="Tags / Palavras-chave" optional>
              <input className="input-base" name="tags" placeholder="capulana, vestido, angola, tradicional..." value={form.tags} onChange={handleChange} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>Separe com vírgulas. Ajuda compradores a encontrar o produto.</span>
            </Field>

            <Toggle name="has_variants" label="Tem variantes?" sub="Tamanhos, cores ou modelos diferentes" />

            {form.has_variants && (
              <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>Ex: S, M, L, XL — Vermelho, Azul, Verde</p>
                <input className="input-base" name="variants_text" placeholder="S, M, L, XL" value={form.variants_text} onChange={handleChange} />
              </div>
            )}
          </>}

          {/* Step 3 */}
          {step === 3 && <>
            <Toggle name="express" label="Entrega Express" sub="Entrega no mesmo dia em Luanda" />
            <Toggle name="free_shipping" label="Envio grátis" sub="Absorver o custo de envio" />

            <Field name="weight" label="Peso (kg)" optional>
              <input className="input-base" name="weight" type="number" placeholder="0.5" value={form.weight} onChange={handleChange} />
            </Field>

            <Field name="processing_time" label="Tempo de preparação">
              <select className="input-base" name="processing_time" value={form.processing_time} onChange={handleChange} style={{ appearance: 'none', cursor: 'pointer' }}>
                {PROCESSING_TIMES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>

            {/* Preview card */}
            <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #C9A84C', padding: 16 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#C9A84C', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 14 }}>Pré-visualização do produto</p>
              {[
                { l: 'Nome', v: form.name || '—' },
                { l: 'Categoria', v: form.category || '—' },
                { l: 'Estado', v: CONDITIONS.find(c => c.value === form.condition)?.label || '—' },
                { l: 'Preço', v: form.price ? `${Number(form.price).toLocaleString()} Kz` : '—' },
                { l: 'Desconto', v: discount ? `-${discount}%` : 'Sem desconto' },
                { l: 'Stock', v: form.stock || '—' },
                { l: 'Express', v: form.express ? '✓ Sim' : '✗ Não' },
                { l: 'Envio grátis', v: form.free_shipping ? '✓ Sim' : '✗ Não' },
                { l: 'Preparação', v: form.processing_time },
              ].map(row => (
                <div key={row.l} style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, marginBottom: 8, borderBottom: '1px solid #1E1E1E' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{row.l}</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>{row.v}</span>
                </div>
              ))}
            </div>
          </>}

          {/* Nav buttons */}
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button type="button" onClick={() => step > 1 ? setStep(s => s - 1) : navigate('/seller/products')}
              className="btn-secondary" style={{ flex: step > 1 ? 1 : 0, padding: step > 1 ? undefined : '1rem 20px', width: step > 1 ? undefined : 'auto' }}>
              {step > 1 ? 'Anterior' : 'Cancelar'}
            </button>
            {step < 3 ? (
              <button type="button" className="btn-primary" onClick={handleNext} style={{ flex: 1 }}>Próximo</button>
            ) : (
              <button type="button" className="btn-primary" onClick={handleSubmit} disabled={loading} style={{ flex: 1, opacity: loading ? 0.7 : 1 }}>
                {loading ? 'A publicar...' : '🚀 Publicar produto'}
              </button>
            )}
          </div>
        </div>
      </div>
    </SellerLayout>
  )
}
