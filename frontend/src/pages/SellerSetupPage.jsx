import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const CATEGORIES = ['Moda', 'Tecnologia', 'Casa & Jardim', 'Beleza', 'Alimentação', 'Desporto', 'Crianças', 'Arte & Artesanato', 'Outro']
const PROVINCES = ['Luanda', 'Benguela', 'Huambo', 'Bié', 'Huíla', 'Cabinda', 'Uíge', 'Namibe', 'Malanje', 'Cunene', 'Moxico', 'Cuando Cubango', 'Lunda Norte', 'Lunda Sul', 'Kwanza Norte', 'Kwanza Sul', 'Bengo', 'Zaire']
const DAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

export default function SellerSetupPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    store_name: '', category: '', description: '',
    nif: '', province: 'Luanda', phone: '', whatsapp: '',
    instagram: '', returns_policy: '',
  })
  const [workingDays, setWorkingDays] = useState([true, true, true, true, true, false, false])
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleChange = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }))
  const toggleDay = (i) => setWorkingDays(d => d.map((v, idx) => idx === i ? !v : v))

  const handleSave = async () => {
    if (!form.store_name.trim()) { alert('Insira o nome da loja.'); return }
    setLoading(true)
    // TODO: call sellerAPI.setupStore(form) when backend is ready
    await new Promise(r => setTimeout(r, 1000))
    setSaved(true)
    setLoading(false)
    setTimeout(() => navigate('/seller'), 1500)
  }

  const Label = ({ children, optional }) => (
    <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
      {children}{optional && <span style={{ color: '#555', fontWeight: 400 }}> (opcional)</span>}
    </label>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      {/* Header */}
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <button onClick={() => navigate('/seller')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
            Configurar loja
          </h1>
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Logo upload */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 0' }}>
            <div style={{
              width: 90, height: 90, borderRadius: 20,
              background: '#1E1E1E', border: '2px dashed #2A2A2A',
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', gap: 6,
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>Logo da loja</span>
            </div>
          </div>

          {/* Store name */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Nome da loja</Label>
            <input className="input-base" name="store_name" placeholder="Ex: Moda Luanda Premium"
              value={form.store_name} onChange={handleChange} />
          </div>

          {/* Category */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Categoria principal</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {CATEGORIES.map(cat => (
                <button key={cat} onClick={() => setForm(f => ({ ...f, category: cat }))}
                  style={{
                    padding: '7px 14px', borderRadius: 50,
                    border: `1.5px solid ${form.category === cat ? '#C9A84C' : '#2A2A2A'}`,
                    background: form.category === cat ? 'rgba(201,168,76,0.1)' : 'transparent',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 12,
                    color: form.category === cat ? '#C9A84C' : '#9A9A9A',
                    cursor: 'pointer',
                  }}>
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Description */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Descrição da loja</Label>
            <textarea className="input-base" name="description"
              placeholder="Descreva os seus produtos e o que torna a sua loja especial..."
              value={form.description} onChange={handleChange}
              rows={3} style={{ resize: 'none', lineHeight: 1.6 }} />
          </div>

          {/* NIF */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>NIF / Número fiscal</Label>
            <input className="input-base" name="nif" placeholder="000000000"
              value={form.nif} onChange={handleChange} />
          </div>

          {/* Province */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Província</Label>
            <select className="input-base" name="province" value={form.province} onChange={handleChange}
              style={{ appearance: 'none', cursor: 'pointer' }}>
              {PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {/* Working hours */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Label>Dias de funcionamento</Label>
            <div style={{ display: 'flex', gap: 8 }}>
              {DAYS.map((day, i) => (
                <button key={day} onClick={() => toggleDay(i)}
                  style={{
                    flex: 1, padding: '8px 0', borderRadius: 10,
                    border: `1.5px solid ${workingDays[i] ? '#C9A84C' : '#2A2A2A'}`,
                    background: workingDays[i] ? 'rgba(201,168,76,0.1)' : 'transparent',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 11,
                    color: workingDays[i] ? '#C9A84C' : '#9A9A9A',
                    cursor: 'pointer',
                  }}>
                  {day}
                </button>
              ))}
            </div>
          </div>

          {/* Contact */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label>Telefone da loja</Label>
            <div style={{ display: 'flex' }}>
              <div style={{
                display: 'flex', alignItems: 'center', padding: '0 14px',
                background: '#1E1E1E', border: '1px solid #2A2A2A',
                borderRight: 'none', borderRadius: '12px 0 0 12px',
                fontFamily: "'DM Sans', sans-serif", fontSize: 14,
                color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap',
              }}>🇦🇴 +244</div>
              <input className="input-base" name="phone" type="tel"
                placeholder="9xx xxx xxx" value={form.phone} onChange={handleChange}
                style={{ borderRadius: '0 12px 12px 0', flex: 1 }} />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>WhatsApp Business</Label>
            <input className="input-base" name="whatsapp" placeholder="+244 9xx xxx xxx"
              value={form.whatsapp} onChange={handleChange} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Instagram</Label>
            <input className="input-base" name="instagram" placeholder="@nome_da_loja"
              value={form.instagram} onChange={handleChange} />
          </div>

          {/* Returns policy */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Label optional>Política de devoluções</Label>
            <textarea className="input-base" name="returns_policy"
              placeholder="Ex: Aceitamos devoluções em até 15 dias após a entrega..."
              value={form.returns_policy} onChange={handleChange}
              rows={3} style={{ resize: 'none', lineHeight: 1.6 }} />
          </div>

          <button className="btn-primary" onClick={handleSave}
            disabled={loading}
            style={{
              marginTop: 8, opacity: loading ? 0.7 : 1,
              background: saved ? '#059669' : '#C9A84C',
              transition: 'background 0.3s',
            }}>
            {saved ? 'Guardado!' : loading ? 'A guardar...' : 'Guardar configurações'}
          </button>
        </div>
      </div>
    </div>
  )
}
