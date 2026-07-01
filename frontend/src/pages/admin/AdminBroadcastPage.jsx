import { useState, useEffect } from 'react'
import AdminLayout from '@/layouts/AdminLayout'
import client from '@/api/client'

const G = '#C9A84C', BG = '#0A0A0A', CARD = '#111', BORDER = '#1E1E1E', TEXT = '#fff', MUTED = '#666', GREEN = '#059669', RED = '#EF4444'

const SEGMENTS = [
  { v: 'all',               l: 'Todos os utilizadores' },
  { v: 'all_buyers',        l: 'Todos os compradores' },
  { v: 'all_sellers',       l: 'Todos os vendedores' },
  { v: 'new_users',         l: 'Novos utilizadores (7 dias)' },
  { v: 'inactive_30',       l: 'Inactivos há 30+ dias' },
  { v: 'province',          l: 'Província específica' },
  { v: 'category_interest', l: 'Interesse de categoria' },
]
const CHANNELS = [
  { v: 'both',  l: 'Push + In-app' },
  { v: 'push',  l: 'Só Push' },
  { v: 'inapp', l: 'Só In-app' },
]
const STATUS_COLORS = { draft: MUTED, scheduled: G, sent: GREEN, failed: RED }
const STATUS_LABELS = { draft: 'Rascunho', scheduled: 'A enviar', sent: 'Enviado', failed: 'Falhou' }

const inputStyle = {
  width: '100%', padding: '11px 14px', background: CARD, border: `1px solid ${BORDER}`,
  borderRadius: 10, color: TEXT, fontFamily: "'DM Sans'", fontSize: 14, outline: 'none', boxSizing: 'border-box',
}

export default function AdminBroadcastPage() {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [toast, setToast] = useState(null)
  const [form, setForm] = useState({ title: '', body: '', segment: 'all', segment_value: '', channel: 'both' })

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3500) }

  const load = () => {
    setLoading(true)
    client.get('/api/v1/notifications/admin/broadcasts/')
      .then(r => setList(r.data.broadcasts || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const needsValue = form.segment === 'province' || form.segment === 'category_interest'
  const canCreate = form.title.trim().length >= 3 && form.body.trim().length >= 5 &&
    (!needsValue || form.segment_value.trim())

  // Create the draft, then immediately send it (one-tap broadcast).
  const createAndSend = async () => {
    if (!canCreate || sending) return
    setSending(true)
    try {
      const res = await client.post('/api/v1/notifications/admin/broadcasts/', {
        title: form.title.trim(), body: form.body.trim(),
        segment: form.segment, segment_value: form.segment_value.trim(), channel: form.channel,
      })
      const { id, estimated_recipients } = res.data
      await client.post(`/api/v1/notifications/admin/broadcasts/${id}/send/`, {})
      showToast(`Enviado para ~${estimated_recipients} utilizadores`)
      setForm({ title: '', body: '', segment: 'all', segment_value: '', channel: 'both' })
      load()
    } catch (e) {
      showToast(e?.response?.data?.error || 'Erro ao enviar broadcast', 'error')
    } finally { setSending(false) }
  }

  return (
    <AdminLayout title="Broadcast">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 90px' }}>
        {toast && <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', background: toast.type === 'error' ? RED : GREEN, color: '#fff', padding: '10px 20px', borderRadius: 10, zIndex: 999, fontFamily: "'DM Sans'", fontSize: 13, maxWidth: '90%', textAlign: 'center' }}>{toast.msg}</div>}

        <h1 style={{ fontFamily: "'Playfair Display'", fontSize: 24, fontWeight: 700, color: TEXT, margin: '0 0 4px' }}>Enviar mensagem</h1>
        <p style={{ fontFamily: "'DM Sans'", fontSize: 13, color: MUTED, margin: '0 0 18px' }}>Envie uma notificação a um segmento de utilizadores.</p>

        {/* Compose */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 26 }}>
          <div>
            <label style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, display: 'block', marginBottom: 6 }}>Destinatários</label>
            <select value={form.segment} onChange={e => setForm(f => ({ ...f, segment: e.target.value }))} style={inputStyle}>
              {SEGMENTS.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
            </select>
          </div>
          {needsValue && (
            <input value={form.segment_value} onChange={e => setForm(f => ({ ...f, segment_value: e.target.value }))}
              placeholder={form.segment === 'province' ? 'Nome da província (ex: Luanda)' : 'Nome da categoria (ex: Moda)'} style={inputStyle} />
          )}
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} maxLength={100}
            placeholder="Título" style={inputStyle} />
          <textarea value={form.body} onChange={e => setForm(f => ({ ...f, body: e.target.value }))} rows={4}
            placeholder="Mensagem…" style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }} />
          <div>
            <label style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, display: 'block', marginBottom: 6 }}>Canal</label>
            <select value={form.channel} onChange={e => setForm(f => ({ ...f, channel: e.target.value }))} style={inputStyle}>
              {CHANNELS.map(c => <option key={c.v} value={c.v}>{c.l}</option>)}
            </select>
          </div>
          <button onClick={createAndSend} disabled={!canCreate || sending}
            style={{ marginTop: 4, padding: '14px 0', borderRadius: 12, border: 'none', background: (!canCreate || sending) ? 'rgba(201,168,76,0.4)' : G, fontFamily: "'DM Sans'", fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: (!canCreate || sending) ? 'default' : 'pointer' }}>
            {sending ? 'A enviar…' : '📢 Enviar broadcast'}
          </button>
        </div>

        {/* History */}
        <h2 style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 10px' }}>Histórico</h2>
        {loading ? (
          <p style={{ fontFamily: "'DM Sans'", fontSize: 13, color: MUTED }}>A carregar…</p>
        ) : list.length === 0 ? (
          <p style={{ fontFamily: "'DM Sans'", fontSize: 13, color: MUTED }}>Ainda não enviou nenhuma mensagem.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {list.map(b => (
              <div key={b.id} style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontFamily: "'DM Sans'", fontSize: 14, fontWeight: 600, color: TEXT, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.title}</span>
                  <span style={{ fontFamily: "'DM Sans'", fontSize: 11, fontWeight: 700, color: STATUS_COLORS[b.status] || MUTED }}>{STATUS_LABELS[b.status] || b.status}</span>
                </div>
                <div style={{ fontFamily: "'DM Sans'", fontSize: 12, color: MUTED }}>
                  {b.segment_label || b.segment} · {b.recipient_count} destinatários
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
