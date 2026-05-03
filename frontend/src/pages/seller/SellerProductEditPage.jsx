import { useState, useRef, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

const CATEGORIES = ['Moda', 'Tecnologia', 'Casa & Jardim', 'Beleza', 'Alimentação', 'Desporto', 'Crianças', 'Arte & Artesanato', 'Acessórios', 'Outro']
const CONDITIONS = [{ value: 'new', label: 'Novo' }, { value: 'used', label: 'Usado' }, { value: 'refurbished', label: 'Recondicionado' }]
const PROCESSING_TIMES = ['Mesmo dia', '1-2 dias úteis', '2-3 dias úteis', '3-5 dias úteis', '5-7 dias úteis']

const S = { fontFamily: "'DM Sans', sans-serif" }

export default function SellerProductEditPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const fileInputRef = useRef(null)

  const [step, setStep] = useState(1)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(true)
  const [toast, setToast] = useState(null)
  const [images, setImages] = useState([]) // { file?: File, preview: string, existing?: true }

  const [form, setForm] = useState({
    name: '', category: '', condition: 'new',
    price: '', original_price: '', stock: '', sku: '',
    description: '', tags: '',
    has_variants: false, variants_text: '',
    express: false, free_shipping: false,
    weight: '', processing_time: '1-2 dias úteis',
  })

  useEffect(() => {
    client.get(`/api/v1/products/${id}/`).then(r => {
      const p = r.data
      setForm({
        name: p.name || '',
        category: p.category || '',
        condition: p.condition || 'new',
        price: p.price ? String(p.price) : '',
        original_price: p.original_price ? String(p.original_price) : '',
        stock: p.stock != null ? String(p.stock) : '',
        sku: p.sku || '',
        description: p.description || '',
        tags: Array.isArray(p.tags) ? p.tags.join(', ') : (p.tags || ''),
        has_variants: !!p.variants,
        variants_text: p.variants || '',
        express: !!p.is_express,
        free_shipping: !!p.free_shipping,
        weight: p.weight ? String(p.weight) : '',
        processing_time: p.processing_time || '1-2 dias úteis',
      })
      // Load existing images
      const existingImgs = []
      if (p.images && Array.isArray(p.images)) {
        p.images.forEach(img => {
          if (img.image) existingImgs.push({ preview: img.image, existing: true, id: img.id })
        })
      } else if (p.image) {
        existingImgs.push({ preview: p.image, existing: true })
      }
      setImages(existingImgs)
    }).catch(() => {
      showToast('Erro ao carregar produto.', 'error')
      setTimeout(() => navigate('/seller/products'), 1500)
    }).finally(() => setFetching(false))
  }, [id])

  const discount = form.price && form.original_price && Number(form.original_price) > Number(form.price)
    ? Math.round((1 - Number(form.price) / Number(form.original_price)) * 100) : null

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
    setErrors(p => ({ ...p, [name]: null }))
  }

  const handleImagesSelected = (e) => {
    const files = Array.from(e.target.files || [])
    const newImgs = files
      .filter(f => f.type.startsWith('image/'))
      .slice(0, 4 - images.length)
      .map(file => ({ file, preview: URL.createObjectURL(file) }))
    setImages(prev => [...prev, ...newImgs].slice(0, 4))
    e.target.value = ''
  }

  const removeImage = (idx) => {
    setImages(prev => {
      const img = prev[idx]
      if (!img.existing) URL.revokeObjectURL(img.preview)
      return prev.filter((_, i) => i !== idx)
    })
  }

  const validate = (s) => {
    const errs = {}
    if (s === 1) {
      if (!form.name.trim()) errs.name = 'Insira o nome do produto'
      if (form.name.length > 100) errs.name = 'Máximo 100 caracteres'
      if (!form.category) errs.category = 'Selecione uma categoria'
      if (!form.price || isNaN(form.price) || Number(form.price) <= 0) errs.price = 'Insira um preço válido'
      if (form.original_price && Number(form.original_price) <= Number(form.price)) errs.original_price = 'Preço original deve ser maior'
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
    if (!validate(3)) return
    setLoading(true)
    try {
      const newImages = images.filter(img => !img.existing && img.file)

      if (newImages.length > 0) {
        const fd = new FormData()
        fd.append('name', form.name.trim())
        fd.append('category', form.category)
        fd.append('condition', form.condition)
        fd.append('price', form.price)
        if (form.original_price) fd.append('original_price', form.original_price)
        fd.append('stock', form.stock)
        if (form.sku) fd.append('sku', form.sku.trim())
        fd.append('description', form.description.trim())
        if (form.tags) fd.append('tags', form.tags.trim())
        fd.append('is_express', form.express ? 'true' : 'false')
        fd.append('free_shipping', form.free_shipping ? 'true' : 'false')
        if (form.weight) fd.append('weight', form.weight)
        fd.append('processing_time', form.processing_time)
        if (form.has_variants && form.variants_text) fd.append('variants', form.variants_text)
        newImages.forEach((img, i) => {
          fd.append(i === 0 ? 'image' : `image_${i + 1}`, img.file, img.file.name)
        })
        await client.patch(`/api/v1/products/${id}/update/`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      } else {
        await client.patch(`/api/v1/products/${id}/update/`, {
          name: form.name.trim(),
          category: form.category,
          condition: form.condition,
          price: form.price,
          original_price: form.original_price || null,
          stock: form.stock,
          sku: form.sku.trim() || null,
          description: form.description.trim(),
          tags: form.tags.trim() || null,
          is_express: form.express,
          free_shipping: form.free_shipping,
          weight: form.weight || null,
          processing_time: form.processing_time,
          variants: form.has_variants ? form.variants_text : null,
        })
      }

      showToast('Produto actualizado com sucesso!')
      setTimeout(() => navigate('/seller/products'), 1200)
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const firstKey = Object.keys(data)[0]
        showToast(Array.isArray(data[firstKey]) ? data[firstKey][0] : data[firstKey] || 'Erro ao actualizar.', 'error')
      } else {
        showToast('Erro ao actualizar produto. Tente novamente.', 'error')
      }
    } finally { setLoading(false) }
  }

  const Toggle = ({ name, label, sub }) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: '14px 16px' }}>
      <div>
        <p style={{ ...S, fontSize: 14, fontWeight: 500, color: '#FFF' }}>{label}</p>
        {sub && <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{sub}</p>}
      </div>
      <div onClick={() => setForm(f => ({ ...f, [name]: !f[name] }))}
        style={{ width: 44, height: 24, borderRadius: 12, background: form[name] ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0 }}>
        <div style={{ position: 'absolute', top: 3, left: form[name] ? 23 : 3, width: 18, height: 18, borderRadius: '50%', background: '#FFF', transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }} />
      </div>
    </div>
  )

  const Field = ({ name, label, optional, error, children }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ ...S, fontSize: 12, fontWeight: 500, color: error ? '#F87171' : '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        {label}{optional && <span style={{ color: '#555', fontWeight: 400 }}> (opcional)</span>}
      </label>
      {children}
      {error && <span style={{ ...S, fontSize: 11, color: '#F87171' }}>{error}</span>}
    </div>
  )

  const inputStyle = { width: '100%', background: '#141414', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', ...S, fontSize: 14, color: '#FFF', outline: 'none', boxSizing: 'border-box' }

  if (fetching) {
    return (
      <SellerLayout title="Editar produto">
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: 28, height: 28, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
          </div>
        </div>
      </SellerLayout>
    )
  }

  return (
    <SellerLayout title="Editar produto">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFF', padding: '10px 20px', borderRadius: 12, ...S, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      {/* Step indicator */}
      <div style={{ padding: '8px 20px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          {['Informações', 'Descrição', 'Entrega'].map((label, i) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', flex: i < 2 ? 1 : 'none' }}>
              <button onClick={() => i + 1 < step && setStep(i + 1)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: i + 1 < step ? 'pointer' : 'default', padding: 0 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, background: step > i + 1 ? '#059669' : step === i + 1 ? '#C9A84C' : '#2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background 0.3s' }}>
                  {step > i + 1
                    ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12" /></svg>
                    : <span style={{ ...S, fontSize: 10, fontWeight: 700, color: step === i + 1 ? '#0A0A0A' : '#9A9A9A' }}>{i + 1}</span>
                  }
                </div>
                <span style={{ ...S, fontSize: 11, color: step === i + 1 ? '#C9A84C' : step > i + 1 ? '#059669' : '#9A9A9A' }}>{label}</span>
              </button>
              {i < 2 && <div style={{ flex: 1, height: 1, background: step > i + 1 ? '#059669' : '#2A2A2A', margin: '0 8px', transition: 'background 0.3s' }} />}
            </div>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* ── Step 1 ── */}
          {step === 1 && <>
            <div>
              <label style={{ ...S, fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase', display: 'block', marginBottom: 8 }}>
                Fotos do produto <span style={{ color: '#555', fontWeight: 400 }}>(até 4)</span>
              </label>
              <input ref={fileInputRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={handleImagesSelected} />
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {images.map((img, i) => (
                  <div key={i} style={{ width: 80, height: 80, borderRadius: 12, position: 'relative', overflow: 'hidden', flexShrink: 0, border: i === 0 ? '2px solid #C9A84C' : '1px solid #2A2A2A' }}>
                    <img src={img.preview} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    {i === 0 && (
                      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, background: 'rgba(201,168,76,0.85)', padding: '2px 0', textAlign: 'center' }}>
                        <span style={{ ...S, fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>Principal</span>
                      </div>
                    )}
                    <button onClick={() => removeImage(i)}
                      style={{ position: 'absolute', top: 4, right: 4, width: 20, height: 20, borderRadius: '50%', background: 'rgba(0,0,0,0.7)', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                    </button>
                  </div>
                ))}
                {images.length < 4 && (
                  <button onClick={() => fileInputRef.current?.click()}
                    style={{ width: 80, height: 80, borderRadius: 12, background: '#1E1E1E', border: '2px dashed #2A2A2A', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', gap: 4, flexShrink: 0 }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.8" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
                    <span style={{ ...S, fontSize: 9, color: '#555' }}>Adicionar</span>
                  </button>
                )}
              </div>
            </div>

            <Field name="name" label="Nome do produto" error={errors.name}>
              <input name="name" placeholder="Ex: Vestido Capulana Premium Tamanho M" value={form.name} onChange={handleChange}
                style={{ ...inputStyle, borderColor: errors.name ? 'rgba(220,38,38,0.5)' : '#2A2A2A' }} />
              <span style={{ ...S, fontSize: 11, color: form.name.length > 90 ? '#f59e0b' : '#555' }}>{form.name.length}/100</span>
            </Field>

            <Field name="category" label="Categoria" error={errors.category}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {CATEGORIES.map(cat => (
                  <button key={cat} type="button" onClick={() => { setForm(f => ({ ...f, category: cat })); setErrors(e => ({ ...e, category: null })) }}
                    style={{ padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${form.category === cat ? '#C9A84C' : errors.category ? 'rgba(220,38,38,0.3)' : '#2A2A2A'}`, background: form.category === cat ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: form.category === cat ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                    {cat}
                  </button>
                ))}
              </div>
            </Field>

            <div>
              <label style={{ ...S, fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase', display: 'block', marginBottom: 8 }}>Estado</label>
              <div style={{ display: 'flex', gap: 10 }}>
                {CONDITIONS.map(c => (
                  <button key={c.value} type="button" onClick={() => setForm(f => ({ ...f, condition: c.value }))}
                    style={{ flex: 1, padding: '10px 0', borderRadius: 12, cursor: 'pointer', border: `1.5px solid ${form.condition === c.value ? '#C9A84C' : '#2A2A2A'}`, background: form.condition === c.value ? 'rgba(201,168,76,0.1)' : '#141414', ...S, fontSize: 12, fontWeight: 500, color: form.condition === c.value ? '#C9A84C' : '#9A9A9A' }}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <Field name="price" label="Preço (Kz)" error={errors.price}>
                <input name="price" type="number" inputMode="numeric" placeholder="0" value={form.price} onChange={handleChange}
                  style={{ ...inputStyle, borderColor: errors.price ? 'rgba(220,38,38,0.5)' : '#2A2A2A' }} />
              </Field>
              <Field name="original_price" label="Preço original" optional error={errors.original_price}>
                <input name="original_price" type="number" inputMode="numeric" placeholder="0" value={form.original_price} onChange={handleChange}
                  style={{ ...inputStyle, borderColor: errors.original_price ? 'rgba(220,38,38,0.5)' : '#2A2A2A' }} />
              </Field>
            </div>

            {discount && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 10, padding: '10px 14px' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round"><polyline points="20 6 9 17 4 12" /></svg>
                <span style={{ ...S, fontSize: 12, color: '#059669' }}>Desconto de {discount}% será exibido aos compradores</span>
              </div>
            )}

            <div style={{ display: 'flex', gap: 12 }}>
              <Field name="stock" label="Stock" error={errors.stock}>
                <input name="stock" type="number" inputMode="numeric" placeholder="0" value={form.stock} onChange={handleChange}
                  style={{ ...inputStyle, borderColor: errors.stock ? 'rgba(220,38,38,0.5)' : '#2A2A2A' }} />
              </Field>
              <Field name="sku" label="SKU" optional>
                <input name="sku" placeholder="SKU-001" value={form.sku} onChange={handleChange} style={inputStyle} />
              </Field>
            </div>
          </>}

          {/* ── Step 2 ── */}
          {step === 2 && <>
            <Field name="description" label="Descrição detalhada" error={errors.description}>
              <textarea name="description"
                placeholder="Descreva o produto em detalhe: materiais, tamanhos, cores, cuidados, origem..."
                value={form.description} onChange={handleChange}
                rows={6} style={{ ...inputStyle, resize: 'none', lineHeight: 1.6, borderColor: errors.description ? 'rgba(220,38,38,0.5)' : '#2A2A2A' }} />
              <span style={{ ...S, fontSize: 11, color: form.description.length > 1800 ? '#f59e0b' : '#555' }}>{form.description.length}/2000</span>
            </Field>

            <Field name="tags" label="Tags / Palavras-chave" optional>
              <input name="tags" placeholder="capulana, vestido, angola, tradicional..." value={form.tags} onChange={handleChange} style={inputStyle} />
              <span style={{ ...S, fontSize: 11, color: '#555' }}>Separe com vírgulas.</span>
            </Field>

            <Toggle name="has_variants" label="Tem variantes?" sub="Tamanhos, cores ou modelos diferentes" />

            {form.has_variants && (
              <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>Ex: S, M, L, XL — Vermelho, Azul, Verde</p>
                <input name="variants_text" placeholder="S, M, L, XL" value={form.variants_text} onChange={handleChange} style={inputStyle} />
              </div>
            )}
          </>}

          {/* ── Step 3 ── */}
          {step === 3 && <>
            <Toggle name="express" label="Entrega Express" sub="Entrega no mesmo dia em Luanda" />
            <Toggle name="free_shipping" label="Envio grátis" sub="Absorver o custo de envio" />

            <Field name="weight" label="Peso (kg)" optional>
              <input name="weight" type="number" placeholder="0.5" value={form.weight} onChange={handleChange} style={inputStyle} />
            </Field>

            <Field name="processing_time" label="Tempo de preparação">
              <select name="processing_time" value={form.processing_time} onChange={handleChange}
                style={{ ...inputStyle, appearance: 'none', cursor: 'pointer' }}>
                {PROCESSING_TIMES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>

            {/* Preview */}
            <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #C9A84C', padding: 16 }}>
              <p style={{ ...S, fontSize: 11, fontWeight: 600, color: '#C9A84C', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 14 }}>Pré-visualização</p>
              {images[0] && (
                <img src={images[0].preview} alt="" style={{ width: '100%', height: 160, objectFit: 'cover', borderRadius: 10, marginBottom: 12 }} />
              )}
              {[
                { l: 'Nome', v: form.name || '—' },
                { l: 'Categoria', v: form.category || '—' },
                { l: 'Estado', v: CONDITIONS.find(c => c.value === form.condition)?.label || '—' },
                { l: 'Preço', v: form.price ? `${Number(form.price).toLocaleString()} Kz` : '—' },
                { l: 'Desconto', v: discount ? `-${discount}%` : 'Sem desconto' },
                { l: 'Stock', v: form.stock || '—' },
                { l: 'Express', v: form.express ? '✓ Sim' : '✗ Não' },
                { l: 'Envio grátis', v: form.free_shipping ? '✓ Sim' : '✗ Não' },
              ].map(row => (
                <div key={row.l} style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, marginBottom: 8, borderBottom: '1px solid #1E1E1E' }}>
                  <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>{row.l}</span>
                  <span style={{ ...S, fontSize: 13, color: '#FFF', fontWeight: 500 }}>{row.v}</span>
                </div>
              ))}
            </div>
          </>}

          {/* Navigation */}
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button type="button" onClick={() => step > 1 ? setStep(s => s - 1) : navigate('/seller/products')}
              style={{ padding: '13px 20px', borderRadius: 14, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 14, color: '#9A9A9A', cursor: 'pointer', flex: step > 1 ? 1 : 'none' }}>
              {step > 1 ? 'Anterior' : 'Cancelar'}
            </button>
            {step < 3 ? (
              <button type="button" onClick={handleNext}
                style={{ flex: 1, padding: '13px 0', borderRadius: 14, border: 'none', background: '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                Próximo →
              </button>
            ) : (
              <button type="button" onClick={handleSubmit} disabled={loading}
                style={{ flex: 1, padding: '13px 0', borderRadius: 14, border: 'none', background: loading ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: loading ? 'default' : 'pointer' }}>
                {loading ? 'A guardar...' : '✓ Guardar alterações'}
              </button>
            )}
          </div>
        </div>
      </div>
    </SellerLayout>
  )
}
