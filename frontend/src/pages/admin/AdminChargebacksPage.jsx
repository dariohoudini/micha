/**
 * AdminChargebacksPage
 * ─────────────────────
 * Consumes R2 backend:
 *   GET  /api/v1/payments/chargebacks/[?status=&overdue=1]
 *   POST .../<id>/respond/    { evidence }
 *   POST .../<id>/accept/     { note }
 *   POST .../<id>/resolve/    { won, note }
 */
import { useCallback, useEffect, useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'


const STATUS_COLOR = {
  received: { bg: 'rgba(239,68,68,0.15)',  fg: '#F87171' },
  evidence: { bg: 'rgba(245,158,11,0.12)', fg: '#FBBF24' },
  won:      { bg: 'rgba(34,197,94,0.12)',  fg: '#4ADE80' },
  lost:     { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' },
  accepted: { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' },
}


function Pill({ value }) {
  const c = STATUS_COLOR[value] || { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' }
  return (
    <span style={{
      background: c.bg, color: c.fg,
      padding: '3px 9px', borderRadius: 999,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
    }}>{value}</span>
  )
}


function ChargebackRow({ row, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const act = async (path, body = {}) => {
    setBusy(true); setError('')
    try {
      const { data } = await client.post(
        `/api/v1/payments/chargebacks/${row.id}/${path}/`, body,
      )
      onChanged?.(data)
    } catch (e) {
      setError(e?.response?.data?.detail || 'Falhou')
    } finally {
      setBusy(false)
    }
  }

  const isTerminal = ['won', 'lost', 'accepted'].includes(row.status)
  const due = row.deadline_at && new Date(row.deadline_at)
  const overdue = row.overdue

  return (
    <div style={{
      background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`,
      borderRadius: 12, padding: 14, marginBottom: 12,
    }}>
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8,
        flexWrap: 'wrap',
      }}>
        <Pill value={row.status} />
        {overdue && (
          <span style={{
            background: 'rgba(239,68,68,0.2)', color: '#F87171',
            padding: '3px 9px', borderRadius: 999,
            fontSize: 11, fontWeight: 600,
          }}>OVERDUE</span>
        )}
        <span style={{ fontSize: 12, color: ADMIN_COLORS.muted }}>
          Case #{row.external_case_id}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: ADMIN_COLORS.muted }}>
          {due ? `Due ${due.toLocaleDateString()}` : ''}
        </span>
      </div>

      <div style={{ fontSize: 16, color: ADMIN_COLORS.text, marginBottom: 4 }}>
        {row.amount} {row.currency} — {row.reason_code}
      </div>

      {row.reason_text && (
        <div style={{ fontSize: 13, color: ADMIN_COLORS.muted, marginBottom: 8 }}>
          {row.reason_text}
        </div>
      )}

      <div style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 10 }}>
        Order: {row.order_id || '—'} | Payment: {row.payment_id || '—'}
      </div>

      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', color: '#F87171',
          padding: 8, borderRadius: 6, marginBottom: 8, fontSize: 12,
        }}>{error}</div>
      )}

      {!isTerminal && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {row.status === 'received' && (
            <>
              <button onClick={() => {
                const note = prompt('Evidence summary?') || ''
                act('respond', { evidence: { admin_note: note } })
              }} disabled={busy} style={btnStyle('#22C55E')}>
                Submit Evidence
              </button>
              <button onClick={() => {
                const note = prompt('Reason for accepting loss?') || ''
                act('accept', { note })
              }} disabled={busy} style={btnStyle('#94A3B8')}>
                Accept Loss
              </button>
            </>
          )}
          {row.status === 'evidence' && (
            <>
              <button onClick={() => {
                const note = prompt('Resolution note?') || ''
                act('resolve', { won: true, note })
              }} disabled={busy} style={btnStyle('#22C55E')}>
                Mark Won
              </button>
              <button onClick={() => {
                const note = prompt('Resolution note?') || ''
                act('resolve', { won: false, note })
              }} disabled={busy} style={btnStyle('#EF4444')}>
                Mark Lost
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function btnStyle(color) {
  return {
    background: 'transparent', color,
    border: `1px solid ${color}55`,
    padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600,
    cursor: 'pointer',
  }
}


export default function AdminChargebacksPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('open')  // open | overdue | all

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filter === 'overdue') params.overdue = 1
      else if (filter !== 'all') params.status = 'received'
      const { data } = await client.get('/api/v1/payments/chargebacks/', { params })
      setRows(data?.results || [])
    } catch {
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { load() }, [load])

  return (
    <AdminLayout title="Chargebacks">
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {['open', 'overdue', 'all'].map(v => (
            <button key={v}
                    onClick={() => setFilter(v)}
                    style={{
                      background: filter === v ? '#6366F1' : 'transparent',
                      color: filter === v ? 'white' : ADMIN_COLORS.text,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      padding: '6px 14px', borderRadius: 6,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      textTransform: 'capitalize',
                    }}>{v}</button>
          ))}
        </div>

        {loading ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20 }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20, textAlign: 'center' }}>
            No chargebacks.
          </div>
        ) : (
          rows.map(r => (
            <ChargebackRow key={r.id} row={r}
                           onChanged={() => load()} />
          ))
        )}
      </div>
    </AdminLayout>
  )
}
