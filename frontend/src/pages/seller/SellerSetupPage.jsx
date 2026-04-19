import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'

const CATEGORIES = ['Moda', 'Tecnologia', 'Casa & Jardim', 'Beleza', 'Alimentação', 'Desporto', 'Crianças', 'Arte & Artesanato', 'Acessórios', 'Outro']
const PROVINCES = ['Luanda', 'Benguela', 'Huambo', 'Bié', 'Huíla', 'Cabinda', 'Uíge', 'Namibe', 'Malanje', 'Cunene', 'Moxico', 'Cuando Cubango', 'Lunda Norte', 'Lunda Sul', 'Kwanza Norte', 'Kwanza Sul', 'Bengo', 'Zaire']
const DAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
const PROCESSING_TIMES = ['Mesmo dia', '1-2 dias úteis', '2-3 dias úteis', '3-5 dias úteis', '5-7 dias úteis']

const TABS = [
  { v: 'store', l: 'Loja' },
  { v: 'contact', l: 'Contacto' },
  { v: 'policy', l: 'Políticas' },
]

export default function SellerSetupPage() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('store')
  const [workingDays, setWorkingDays] = useState([true, true, true, true, true, false, false])
  const [savedTabs, setSavedTabs] = useState({ store: false, contact: false, policy: false })
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const [errors, setErrors] = useState({})

  const [storeForm, setStoreForm] = useState({ store_name: '', category: '', description: '', nif: '', province: 'Luanda' })
  const [contactForm, setContactForm] = useState({ phone: '', whatsapp: '', instagram: '' })
  const [policyForm, setPolicyForm] = useState({ returns_policy: '', shipping_policy: '', min_order: '', processing_time: '1-2 dias úteis' })

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const toggleDay = (i) => setWorkingDays(d => d.map((v, idx) => idx === i ? !v : v))

  const validateStore = () => {
    const errs = {}
    if (!storeForm.store_name.trim()) errs.store_name = 'Insira o nome da loja'
    if (!storeForm.category) errs.category = 'Selecione uma categoria'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const validateContact = () => {
    const errs = {}
    if (!contactForm.phone || contactForm.phone.replace(/\s/g, '').length < 9) errs.phone = 'Insira um número válido'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSave = async () => {
    let valid = true
    if (activeTab === 'store') valid = validateStore()
    if (activeTab === 'contact') valid = validateContact()
    if (!valid) return

    setLoading(true)
    await new Promise(r => setTimeout(r, 800))
    setLoading(false)
    setSavedTabs(prev => ({ ...prev, [activeTab]: true }))
    showToast(`${TABS.find(t => t.v === activeTab)?.l} guardado com sucesso!`)
  }

  const Label = ({ children, optional }) => (
    <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
      {children}{optional && <span style={{ color: '#555', fontWeight: 400 }}> (opcional)</span>}
    </label>
  )

  return (
    <SellerLayout title="Configurar Loja">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', padding: '0 16px', gap: 0, borderBottom: '1px solid #1E1E1E', flexShrink: 0 }}>
        {TABS.map(tab => (
          <button key={tab.v} onClick={() => { setActiveTab(tab.v); setErrors({}) }}
            style={{
              flex: 1, padding: '12px 0', background: 'none', border: 'none', cursor: 'pointer',
              fontFamily: "'DM Sans', sans-serif", fontSize: 13,
              fontWeight: activeTab === tab.v ? 600 : 400,
              color: activeTab === tab.v ? '#C9A84C' : '#9A9A9A',
              borderBottom: `2px solid ${activeTab === tab.v ? '#C9A84C' : 'transparent'}`,
              marginBottom: -1, position: 'relative',
            }}>
            {tab.l}
            {savedTabs[tab.v] && (
              <span style={{ position: 'absolute', top: 10, right: 'calc(50% - 24px)', width: 6, height: 6, borderRadius: '50%', background: '#059669' }} />
            )}
          </button>
        ))}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* STORE TAB */}
          {activeTab === 'store' && <>
            {/* Logo */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ width: 80, height: 80, borderRadius: 18, background: '#1E1E1E', border: '2px dashed #2A2A2A', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', gap: 4, flexShrink: 0 }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                </svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: '#9A9A9A' }}>Logo</span>
              </div>
              <div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500, marginBottom: 4 }}>Logo da loja</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', lineHeight: 1.5 }}>PNG ou JPG, mínimo 200×200px</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label>Nome da loja</Label>
              <input className="input-base" placeholder="Ex: Moda Luanda Premium"
                value={storeForm.store_name}
                onChange={e => { setStoreForm(f => ({ ...f, store_name: e.target.value })); setErrors(er => ({ ...er, store_name: null })) }}
                style={{ borderColor: errors.store_name ? 'rgba(220,38,38,0.5)' : undefined }} />
              {errors.store_name && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{errors.store_name}</p>}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Label>Categoria principal</Label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {CATEGORIES.map(cat => (
                  <button key={cat} type="button"
                    onClick={() => { setStoreForm(f => ({ ...f, category: cat })); setErrors(er => ({ ...er, category: null })) }}
                    style={{ padding: '7px 14px', borderRadius: 50, border: `1.5px solid ${storeForm.category === cat ? '#C9A84C' : errors.category ? 'rgba(220,38,38,0.3)' : '#2A2A2A'}`, background: storeForm.category === cat ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: storeForm.category === cat ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                    {cat}
                  </button>
                ))}
              </div>
              {errors.category && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{errors.category}</p>}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label optional>Descrição</Label>
              <textarea className="input-base" placeholder="Descreva a sua loja..." rows={3}
                value={storeForm.description}
                onChange={e => setStoreForm(f => ({ ...f, description: e.target.value }))}
                style={{ resize: 'none', lineHeight: 1.6 }} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>{storeForm.description.length}/500 caracteres</span>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label optional>NIF fiscal</Label>
                <input className="input-base" placeholder="000000000" value={storeForm.nif} onChange={e => setStoreForm(f => ({ ...f, nif: e.target.value }))} />
              </div>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Província</Label>
                <select className="input-base" value={storeForm.province} onChange={e => setStoreForm(f => ({ ...f, province: e.target.value }))} style={{ appearance: 'none', cursor: 'pointer' }}>
                  {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Label>Dias de funcionamento</Label>
              <div style={{ display: 'flex', gap: 6 }}>
                {DAYS.map((day, i) => (
                  <button key={day} type="button" onClick={() => toggleDay(i)}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `1.5px solid ${workingDays[i] ? '#C9A84C' : '#2A2A2A'}`, background: workingDays[i] ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: workingDays[i] ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                    {day}
                  </button>
                ))}
              </div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>
                Activos: {workingDays.map((v, i) => v ? DAYS[i] : null).filter(Boolean).join(', ')}
              </p>
            </div>
          </>}

          {/* CONTACT TAB */}
          {activeTab === 'contact' && <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label>Telefone da loja</Label>
              <div style={{ display: 'flex' }}>
                <div style={{ display: 'flex', alignItems: 'center', padding: '0 14px', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRight: 'none', borderRadius: '12px 0 0 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap' }}>🇦🇴 +244</div>
                <input className="input-base" type="tel" inputMode="numeric" placeholder="9xx xxx xxx"
                  value={contactForm.phone}
                  onChange={e => { setContactForm(f => ({ ...f, phone: e.target.value })); setErrors(er => ({ ...er, phone: null })) }}
                  style={{ borderRadius: '0 12px 12px 0', flex: 1, borderColor: errors.phone ? 'rgba(220,38,38,0.5)' : undefined }} />
              </div>
              {errors.phone && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{errors.phone}</p>}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label optional>WhatsApp Business</Label>
              <div style={{ display: 'flex' }}>
                <div style={{ display: 'flex', alignItems: 'center', padding: '0 14px', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRight: 'none', borderRadius: '12px 0 0 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#25D366', fontWeight: 600, whiteSpace: 'nowrap' }}>WA</div>
                <input className="input-base" type="tel" placeholder="+244 9xx xxx xxx" value={contactForm.whatsapp} onChange={e => setContactForm(f => ({ ...f, whatsapp: e.target.value }))} style={{ borderRadius: '0 12px 12px 0', flex: 1 }} />
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label optional>Instagram</Label>
              <div style={{ display: 'flex' }}>
                <div style={{ display: 'flex', alignItems: 'center', padding: '0 12px', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRight: 'none', borderRadius: '12px 0 0 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#E1306C', whiteSpace: 'nowrap' }}>@</div>
                <input className="input-base" placeholder="nome_da_loja" value={contactForm.instagram} onChange={e => setContactForm(f => ({ ...f, instagram: e.target.value }))} style={{ borderRadius: '0 12px 12px 0', flex: 1 }} />
              </div>
            </div>

            {/* Preview */}
            {(contactForm.phone || contactForm.whatsapp || contactForm.instagram) && (
              <div style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: 14 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Como aparece na sua loja</p>
                {contactForm.phone && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', marginBottom: 6 }}>📞 +244 {contactForm.phone}</p>}
                {contactForm.whatsapp && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', marginBottom: 6 }}>💬 {contactForm.whatsapp}</p>}
                {contactForm.instagram && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>📷 @{contactForm.instagram}</p>}
              </div>
            )}
          </>}

          {/* POLICY TAB */}
          {activeTab === 'policy' && <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label optional>Política de devoluções</Label>
              <textarea className="input-base" placeholder="Ex: Aceitamos devoluções em até 15 dias. Produto deve estar sem uso e na embalagem original..."
                value={policyForm.returns_policy} onChange={e => setPolicyForm(f => ({ ...f, returns_policy: e.target.value }))}
                rows={4} style={{ resize: 'none', lineHeight: 1.6 }} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Label optional>Política de envio</Label>
              <textarea className="input-base" placeholder="Ex: Enviamos em 1-2 dias úteis após confirmação do pagamento. Entrega express disponível em Luanda..."
                value={policyForm.shipping_policy} onChange={e => setPolicyForm(f => ({ ...f, shipping_policy: e.target.value }))}
                rows={3} style={{ resize: 'none', lineHeight: 1.6 }} />
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label optional>Pedido mínimo (Kz)</Label>
                <input className="input-base" type="number" inputMode="numeric" placeholder="0"
                  value={policyForm.min_order} onChange={e => setPolicyForm(f => ({ ...f, min_order: e.target.value }))} />
              </div>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Label>Preparação</Label>
                <select className="input-base" value={policyForm.processing_time} onChange={e => setPolicyForm(f => ({ ...f, processing_time: e.target.value }))} style={{ appearance: 'none', cursor: 'pointer' }}>
                  {PROCESSING_TIMES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>

            {/* Default policies hint */}
            <div style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 12, padding: 14 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', fontWeight: 600, marginBottom: 6 }}>💡 Boas práticas</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.5 }}>
                Lojas com políticas claras têm 40% mais conversões. Seja específico sobre prazos e condições.
              </p>
            </div>
          </>}

          {/* Save button */}
          <button className="btn-primary" onClick={handleSave} disabled={loading}
            style={{ marginTop: 4, opacity: loading ? 0.7 : 1 }}>
            {loading ? 'A guardar...' : `Guardar ${TABS.find(t => t.v === activeTab)?.l}`}
          </button>

        </div>
      </div>
    </SellerLayout>
  )
}
