/**
 * AdminModerationQueuePage
 * ─────────────────────────
 * Moderator-facing queue for the R4 backend:
 *   GET  /api/v1/moderation/queue/[?status=&target_type=&severity=]
 *   POST .../queue/<id>/approve/
 *   POST .../queue/<id>/reject/
 *   POST .../queue/<id>/escalate/
 *
 * Three actions: approve (dismiss), reject (counts as infraction →
 * escalation engine runs), escalate (kick to senior mod). Each
 * displays a confirmation note prompt + shows the escalation result
 * on reject (e.g., "user suspended at 3 infractions").
 */
import { useCallback, useEffect, useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'


const SEVERITY_COLOR = {
  low:    { bg: 'rgba(34,197,94,0.12)',  fg: '#4ADE80' },
  medium: { bg: 'rgba(245,158,11,0.12)', fg: '#FBBF24' },
  high:   { bg: 'rgba(239,68,68,0.15)',  fg: '#F87171' },
}
const STATUS_COLOR = {
  pending:   { bg: 'rgba(99,102,241,0.12)', fg: '#A5B4FC' },
  escalated: { bg: 'rgba(168,85,247,0.12)', fg: '#C084FC' },
  approved:  { bg: 'rgba(34,197,94,0.12)',  fg: '#4ADE80' },
  rejected:  { bg: 'rgba(239,68,68,0.15)',  fg: '#F87171' },
}


function Pill({ value, palette }) {
  const c = palette[value] || { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' }
  return (
    <span style={{
      background: c.bg, color: c.fg,
      padding: '3px 9px', borderRadius: 999,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
      letterSpacing: 0.5,
    }}>{value}</span>
  )
}


function FlagRow({ row, onAction }) {
  const [busy, setBusy] = useState(false)
  const [showNote, setShowNote] = useState(null)  // null | 'approve' | 'reject' | 'escalate'
  const [note, setNote] = useState('')
  const [result, setResult] = useState(null)

  const act = async (action) => {
    setBusy(true)
    try {
      const { data } = await client.post(
        `/api/v1/moderation/queue/${row.id}/${action}/`,
        { note },
      )
      setResult(data)
      onAction?.(row.id, data)
    } catch (e) {
      setResult({ error: e?.response?.data?.detail || 'Falhou' })
    } finally {
      setBusy(false)
      setShowNote(null)
      setNote('')
    }
  }

  return (
    <div style={{
      background: ADMIN_COLORS.card, border: `1px solid ${ADMIN_COLORS.border}`,
      borderRadius: 12, padding: 14, marginBottom: 12,
    }}>
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8,
        flexWrap: 'wrap',
      }}>
        <Pill value={row.status} palette={STATUS_COLOR} />
        <Pill value={row.severity} palette={SEVERITY_COLOR} />
        <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>
          {row.target_type}#{row.target_id}
        </span>
        {row.auto_flagged && (
          <span style={{
            fontSize: 10, color: ADMIN_COLORS.muted,
            border: `1px solid ${ADMIN_COLORS.border}`,
            padding: '2px 6px', borderRadius: 6,
          }}>AUTO</span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: ADMIN_COLORS.muted }}>
          {new Date(row.created_at).toLocaleString()}
        </span>
      </div>

      <div style={{ fontSize: 14, color: ADMIN_COLORS.text, marginBottom: 6 }}>
        {row.reason}
      </div>

      {row.target_snippet && (
        <div style={{
          fontSize: 13, color: ADMIN_COLORS.muted,
          background: 'rgba(255,255,255,0.02)',
          padding: 8, borderRadius: 6, marginBottom: 8,
          fontStyle: 'italic',
        }}>
          "{row.target_snippet}"
        </div>
      )}

      {row.target_user_email && (
        <div style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 8 }}>
          Owner: {row.target_user_email}
        </div>
      )}

      {result && (
        <div style={{
          background: result.error ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
          color: result.error ? '#F87171' : '#4ADE80',
          padding: 8, borderRadius: 6, marginBottom: 8, fontSize: 12,
        }}>
          {result.error || (
            <>
              ✓ {result.status}
              {result.escalation && result.escalation.action !== 'none' && (
                <> — escalation: <b>{result.escalation.action}</b>{' '}
                  ({result.escalation.infractions} infractions)
                </>
              )}
            </>
          )}
        </div>
      )}

      {showNote && (
        <div style={{ marginBottom: 8 }}>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Reason (optional)"
            style={{
              width: '100%', padding: 8,
              background: ADMIN_COLORS.surface,
              border: `1px solid ${ADMIN_COLORS.border}`,
              borderRadius: 6, color: ADMIN_COLORS.text,
              fontSize: 13,
            }}
            autoFocus
          />
          <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
            <button
              disabled={busy}
              onClick={() => act(showNote)}
              style={{
                background: showNote === 'reject' ? '#EF4444' :
                  showNote === 'escalate' ? '#A855F7' : '#22C55E',
                color: 'white', border: 'none',
                padding: '6px 14px', borderRadius: 6, fontSize: 12,
                fontWeight: 600, cursor: 'pointer',
              }}>Confirm {showNote}</button>
            <button
              disabled={busy}
              onClick={() => setShowNote(null)}
              style={{
                background: 'transparent', color: ADMIN_COLORS.muted,
                border: `1px solid ${ADMIN_COLORS.border}`,
                padding: '6px 14px', borderRadius: 6, fontSize: 12,
                cursor: 'pointer',
              }}>Cancel</button>
          </div>
        </div>
      )}

      {!showNote && !result && (
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => setShowNote('approve')}
                  disabled={busy}
                  style={btnStyle('#22C55E')}>Approve</button>
          <button onClick={() => setShowNote('reject')}
                  disabled={busy}
                  style={btnStyle('#EF4444')}>Reject</button>
          <button onClick={() => setShowNote('escalate')}
                  disabled={busy}
                  style={btnStyle('#A855F7')}>Escalate</button>
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


export default function AdminModerationQueuePage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({
    target_type: '', severity: '', status: '',
  })

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const params = {}
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v })
      const { data } = await client.get('/api/v1/moderation/queue/', { params })
      setItems(data?.results || [])
    } catch (e) {
      setError(e?.response?.data?.detail || 'Falhou a carregar a fila')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => { load() }, [load])

  const onRowAction = (id) => {
    // Remove resolved rows after a small delay so the result message stays visible.
    setTimeout(() => {
      setItems(prev => prev.filter(r => r.id !== id))
    }, 1500)
  }

  return (
    <AdminLayout title="Moderation Queue">
      <div style={{ padding: 16 }}>
        <div style={{
          display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap',
        }}>
          <select value={filters.status}
                  onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))}
                  style={selectStyle}>
            <option value="">all open</option>
            <option value="pending">pending</option>
            <option value="escalated">escalated</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
          </select>
          <select value={filters.severity}
                  onChange={(e) => setFilters(f => ({ ...f, severity: e.target.value }))}
                  style={selectStyle}>
            <option value="">any severity</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
          <select value={filters.target_type}
                  onChange={(e) => setFilters(f => ({ ...f, target_type: e.target.value }))}
                  style={selectStyle}>
            <option value="">all targets</option>
            <option value="product">product</option>
            <option value="listing">listing</option>
            <option value="review">review</option>
            <option value="message">message</option>
          </select>
          <button onClick={load}
                  style={{ ...selectStyle, cursor: 'pointer' }}>
            Refresh
          </button>
        </div>

        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)', color: '#F87171',
            padding: 12, borderRadius: 8, marginBottom: 12,
          }}>{error}</div>
        )}

        {loading ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20 }}>Loading…</div>
        ) : items.length === 0 ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20, textAlign: 'center' }}>
            Queue is empty.
          </div>
        ) : (
          items.map(row => (
            <FlagRow key={row.id} row={row} onAction={onRowAction} />
          ))
        )}
      </div>
    </AdminLayout>
  )
}

const selectStyle = {
  background: ADMIN_COLORS.card,
  border: `1px solid ${ADMIN_COLORS.border}`,
  borderRadius: 6, padding: '6px 10px', fontSize: 12,
  color: ADMIN_COLORS.text,
}
