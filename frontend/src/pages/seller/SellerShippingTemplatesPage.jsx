import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

/**
 * SellerShippingTemplatesPage — /seller/shipping
 *
 * AliExpress §14.1 — managed reusable shipping rule sets. A seller
 * can have many templates; each product can pick one at create time
 * via the product wizard's shipping step. Editing a template affects
 * every product using it (a warning banner makes this clear).
 *
 * Implements:
 *   • §14.1 template list + [+ Create New Template]
 *   • §14.2 template form (name, ship from, processing days)
 *   • §14.3 [+ Add Shipping Method] rows with service, destinations,
 *     min/max days, free toggle, cost, additional-item cost
 *   • §14.4 [Cancel] / [Save] with inline validation
 *   • Spec's "edit affects all products" warning on existing tpl edits
 */

const S = { fontFamily: "'DM Sans', sans-serif" }
const input = {
  width: '100%', background: '#0F0F0F', border: '1px solid #2A2A2A',
  borderRadius: 10, padding: '11px 13px', ...S, fontSize: 13,
  color: '#FFFFFF', outline: 'none', boxSizing: 'border-box',
}
const label = {
  ...S, fontSize: 10, color: '#9A9A9A', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.08em',
  marginBottom: 5, display: 'block',
}

const SERVICES = [
  { v: 'standard',   l: 'Standard' },
  { v: 'express',    l: 'Express' },
  { v: 'economy',    l: 'Economy' },
  { v: 'dhl',        l: 'DHL' },
  { v: 'fedex',      l: 'FedEx' },
  { v: 'ups',        l: 'UPS' },
  { v: 'local_post', l: 'Correios locais' },
  { v: 'custom',     l: 'Personalizado' },
]

const DESTINATION_PRESETS = [
  { v: 'AO',  l: 'Angola' },
  { v: 'ZA',  l: 'África do Sul' },
  { v: 'PT',  l: 'Portugal' },
  { v: 'BR',  l: 'Brasil' },
  { v: 'EU',  l: 'União Europeia' },
  { v: 'WORLDWIDE', l: 'Todo o mundo' },
]

function emptyMethod() {
  return {
    service: 'standard', custom_service_name: '',
    destinations: ['AO'], min_days: 1, max_days: 7,
    free_shipping: false, cost: '0', additional_item_cost: '0',
  }
}

function MethodRow({ m, i, onChange, onRemove }) {
  const upd = (k, v) => onChange({ ...m, [k]: v })
  const toggleDest = (d) => {
    const set = new Set(m.destinations || [])
    set.has(d) ? set.delete(d) : set.add(d)
    upd('destinations', Array.from(set))
  }
  return (
    <div style={{ background: '#0F0F0F', border: '1px solid #1E1E1E', borderRadius: 12, padding: 12, marginBottom: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600, textTransform: 'uppercase' }}>Método {i + 1}</span>
        <button onClick={onRemove} style={{ background: 'none', border: 'none', color: '#ef4444', ...S, fontSize: 11, cursor: 'pointer' }}>Remover</button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <label style={label}>Serviço</label>
          <select value={m.service} onChange={e => upd('service', e.target.value)} style={input}>
            {SERVICES.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
          </select>
        </div>
        {m.service === 'custom' && (
          <input placeholder="Nome do serviço" value={m.custom_service_name} onChange={e => upd('custom_service_name', e.target.value)} style={input} />
        )}
        <div>
          <label style={label}>Destinos</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {DESTINATION_PRESETS.map(d => {
              const on = (m.destinations || []).includes(d.v)
              return (
                <button key={d.v} type="button" onClick={() => toggleDest(d.v)}
                  style={{ padding: '6px 12px', borderRadius: 16, border: `1.5px solid ${on ? '#C9A84C' : '#2A2A2A'}`, background: on ? 'rgba(201,168,76,0.12)' : 'transparent', ...S, fontSize: 11, color: on ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                  {d.l}
                </button>
              )
            })}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <label style={label}>Mín dias</label>
            <input type="number" min="1" value={m.min_days} onChange={e => upd('min_days', Number(e.target.value) || 1)} style={input} />
          </div>
          <div>
            <label style={label}>Máx dias</label>
            <input type="number" min={m.min_days} value={m.max_days} onChange={e => upd('max_days', Number(e.target.value) || 1)} style={input} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
          <span style={{ ...S, fontSize: 12, color: '#FFFFFF' }}>Envio grátis</span>
          <button onClick={() => upd('free_shipping', !m.free_shipping)}
            style={{ width: 40, height: 22, borderRadius: 11, border: 'none', background: m.free_shipping ? '#10b981' : '#2A2A2A', position: 'relative', cursor: 'pointer' }}>
            <div style={{ position: 'absolute', top: 2, left: m.free_shipping ? 20 : 2, width: 18, height: 18, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s' }} />
          </button>
        </div>
        {!m.free_shipping && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <label style={label}>Custo (Kz)</label>
              <input type="number" min="0" value={m.cost} onChange={e => upd('cost', e.target.value)} style={input} />
            </div>
            <div>
              <label style={label}>Por item extra</label>
              <input type="number" min="0" value={m.additional_item_cost} onChange={e => upd('additional_item_cost', e.target.value)} style={input} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function SellerShippingTemplatesPage() {
  const navigate = useNavigate()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)  // template object being edited or 'new'
  const [toast, setToast] = useState(null)
  const [saving, setSaving] = useState(false)

  const show = (m, t = 'success') => { setToast({ m, t }); setTimeout(() => setToast(null), 3000) }
  const reload = () => client.get('/api/v1/shipping/templates/').then(r => setList(r.data?.results || r.data || []))

  useEffect(() => { reload().finally(() => setLoading(false)) }, [])

  const startNew = () => setEditing({
    name: '', ship_from_country: 'Angola',
    processing_days: 2, is_default: list.length === 0,
    methods: [emptyMethod()],
  })

  const save = async () => {
    const t = editing
    if (!t.name.trim()) { show('Nome do template é obrigatório.', 'error'); return }
    if (!(t.methods || []).length) { show('Adicione pelo menos um método.', 'error'); return }
    for (const m of t.methods) {
      if (!(m.destinations || []).length) { show('Cada método precisa de pelo menos 1 destino.', 'error'); return }
    }
    setSaving(true)
    try {
      const body = { ...t, methods: t.methods.map(m => ({
        ...m,
        cost: Number(m.cost || 0),
        additional_item_cost: Number(m.additional_item_cost || 0),
      })) }
      if (t.id) await client.patch(`/api/v1/shipping/templates/${t.id}/`, body)
      else      await client.post('/api/v1/shipping/templates/', body)
      await reload()
      setEditing(null)
      show('Template guardado!')
    } catch (e) {
      show(e.response?.data?.detail || 'Erro ao guardar.', 'error')
    } finally { setSaving(false) }
  }

  const del = async (id) => {
    if (!confirm('Eliminar este template?')) return
    try {
      await client.delete(`/api/v1/shipping/templates/${id}/`)
      await reload()
      show('Template eliminado.')
    } catch { show('Erro ao eliminar.', 'error') }
  }

  // ── Edit form ───────────────────────────────────────────────────
  if (editing) {
    const t = editing
    return (
      <SellerLayout title={t.id ? 'Editar template' : 'Novo template'} showBack>
        {toast && <div style={{ position: 'fixed', top: 70, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {t.id && (
              <div style={{ padding: 12, background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 12 }}>
                <p style={{ ...S, fontSize: 11, color: '#f59e0b', lineHeight: 1.5 }}>
                  ⚠ Alterar este template afecta TODOS os produtos que o usam.
                </p>
              </div>
            )}
            <div>
              <label style={label}>Nome do template *</label>
              <input value={t.name} onChange={e => setEditing({ ...t, name: e.target.value })}
                placeholder="Ex: Envio padrão Luanda" style={input} />
            </div>
            <div>
              <label style={label}>Enviar a partir de</label>
              <input value={t.ship_from_country} onChange={e => setEditing({ ...t, ship_from_country: e.target.value })} style={input} />
            </div>
            <div>
              <label style={label}>Dias de processamento</label>
              <select value={t.processing_days} onChange={e => setEditing({ ...t, processing_days: Number(e.target.value) })} style={input}>
                {[1, 2, 3, 5, 7, 14, 30].map(d => <option key={d} value={d}>{d} dia(s)</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ ...S, fontSize: 13, color: '#FFFFFF' }}>Template predefinido</span>
              <button onClick={() => setEditing({ ...t, is_default: !t.is_default })}
                style={{ width: 44, height: 24, borderRadius: 12, border: 'none', background: t.is_default ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer' }}>
                <div style={{ position: 'absolute', top: 2, left: t.is_default ? 22 : 2, width: 20, height: 20, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s' }} />
              </button>
            </div>

            <div style={{ marginTop: 8 }}>
              <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Métodos de envio</p>
              {(t.methods || []).map((m, i) => (
                <MethodRow key={i} m={m} i={i}
                  onChange={nm => setEditing({ ...t, methods: t.methods.map((x, j) => j === i ? nm : x) })}
                  onRemove={() => setEditing({ ...t, methods: t.methods.filter((_, j) => j !== i) })} />
              ))}
              <button onClick={() => setEditing({ ...t, methods: [...(t.methods || []), emptyMethod()] })}
                style={{ width: '100%', padding: '11px 0', borderRadius: 12, border: '1.5px dashed #C9A84C', background: 'transparent', ...S, fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>
                + Adicionar método
              </button>
            </div>
          </div>
        </div>
        <div style={{ padding: '12px 16px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', borderTop: '1px solid #1A1A1A', background: '#0F0F0F', display: 'flex', gap: 10, flexShrink: 0 }}>
          <button onClick={() => setEditing(null)} style={{ flex: 1, padding: '13px 0', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 13, color: '#FFFFFF', cursor: 'pointer' }}>Cancelar</button>
          <button onClick={save} disabled={saving} style={{ flex: 2, padding: '13px 0', borderRadius: 12, border: 'none', background: saving ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>{saving ? 'A guardar…' : 'Guardar template'}</button>
        </div>
      </SellerLayout>
    )
  }

  // ── List view ───────────────────────────────────────────────────
  return (
    <SellerLayout title="Templates de Envio" showBack>
      {toast && <div style={{ position: 'fixed', top: 70, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.t === 'error' ? '#dc2626' : '#10b981', color: '#FFF', padding: '10px 18px', borderRadius: 14, ...S, fontSize: 13, fontWeight: 600 }}>{toast.m}</div>}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        <div style={{ padding: 16 }}>
          {loading ? (
            <div style={{ height: 80, background: '#141414', borderRadius: 14, animation: 'pulse 1.4s ease-in-out infinite' }}>
              <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.45}}`}</style>
            </div>
          ) : list.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14 }}>
              <p style={{ ...S, fontSize: 14, color: '#FFFFFF', marginBottom: 6 }}>Sem templates ainda</p>
              <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 16 }}>Crie um template para reutilizar regras de envio em vários produtos.</p>
              <button onClick={startNew} style={{ padding: '11px 22px', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>+ Criar primeiro template</button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {list.map(t => (
                <div key={t.id} style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <p style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFFFFF' }}>{t.name}</p>
                      <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>
                        {t.methods?.length || 0} método(s) · {t.processing_days}d processamento
                      </p>
                    </div>
                    {t.is_default && <span style={{ ...S, fontSize: 9, fontWeight: 700, color: '#C9A84C', background: 'rgba(201,168,76,0.12)', padding: '2px 8px', borderRadius: 10, letterSpacing: '0.04em' }}>PADRÃO</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => setEditing({ ...t, methods: [...(t.methods || [])] })}
                      style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 12, color: '#FFFFFF', cursor: 'pointer' }}>
                      Editar
                    </button>
                    <button onClick={() => del(t.id)}
                      style={{ width: 70, padding: '9px 0', borderRadius: 10, border: '1px solid rgba(220,38,38,0.3)', background: 'transparent', ...S, fontSize: 12, color: '#dc2626', cursor: 'pointer' }}>
                      Eliminar
                    </button>
                  </div>
                </div>
              ))}
              <button onClick={startNew} style={{ marginTop: 4, padding: '12px 0', borderRadius: 12, border: '1.5px dashed #C9A84C', background: 'transparent', ...S, fontSize: 13, color: '#C9A84C', cursor: 'pointer' }}>
                + Adicionar template
              </button>
            </div>
          )}
        </div>
      </div>
    </SellerLayout>
  )
}
