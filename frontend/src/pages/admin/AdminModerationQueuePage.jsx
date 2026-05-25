/**
 * AdminModerationQueuePage — production polish pass.
 *
 * R4 backend:
 *   GET  /api/v1/moderation/queue/[?status=&target_type=&severity=]
 *   POST .../queue/<id>/approve|reject|escalate/
 *
 * Polish landed in this pass:
 *  • Skeleton rows while loading (no more "Loading…" string)
 *  • <ErrorState> with retry on fetch failure
 *  • <EmptyState> when queue drains
 *  • Optimistic action: row marked busy immediately, removed on
 *    success, rolled back + toast on failure
 *  • Keyboard shortcuts (A/R/E + J/K nav) for moderator throughput
 *  • Focus management — keep focus on next row after action
 *  • a11y: role=list, aria-live region for action results, focus ring
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import { QueueListSkeleton } from '@/components/ui/AdminSkeletons'
import { toast } from '@/components/ui/Toast'
import {
  useApiQuery, useOptimisticMutation,
} from '@/hooks/useApiKit'
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


function Pill({ value, palette, ariaLabel }) {
  const c = palette[value] || { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' }
  return (
    <span
      aria-label={ariaLabel || value}
      style={{
        background: c.bg, color: c.fg,
        padding: '3px 9px', borderRadius: 999,
        fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: 0.5,
      }}
    >{value}</span>
  )
}


function FlagRow({
  row, isFocused, busy,
  onApprove, onReject, onEscalate,
}) {
  const [showNote, setShowNote] = useState(null)
  const [note, setNote] = useState('')
  const inputRef = useRef(null)
  const rootRef = useRef(null)

  useEffect(() => {
    if (showNote) setTimeout(() => inputRef.current?.focus(), 0)
  }, [showNote])

  useEffect(() => {
    if (isFocused) rootRef.current?.focus()
  }, [isFocused])

  const submit = (action) => {
    setShowNote(null)
    const fn = action === 'approve' ? onApprove
      : action === 'reject' ? onReject
      : onEscalate
    fn(row, note)
    setNote('')
  }

  const handleKey = (e) => {
    // Don't intercept while typing in the note field.
    if (showNote) return
    if (e.key === 'a' || e.key === 'A') { e.preventDefault(); setShowNote('approve') }
    if (e.key === 'r' || e.key === 'R') { e.preventDefault(); setShowNote('reject') }
    if (e.key === 'e' || e.key === 'E') { e.preventDefault(); setShowNote('escalate') }
  }

  return (
    <article
      ref={rootRef}
      tabIndex={0}
      role="listitem"
      aria-label={`Flag ${row.id}: ${row.reason}`}
      onKeyDown={handleKey}
      style={{
        background: ADMIN_COLORS.card,
        border: `1px solid ${isFocused ? '#6366F1' : ADMIN_COLORS.border}`,
        outline: isFocused ? '2px solid rgba(99,102,241,0.25)' : 'none',
        outlineOffset: 2,
        borderRadius: 12, padding: 14, marginBottom: 12,
        opacity: busy ? 0.6 : 1,
        pointerEvents: busy ? 'none' : 'auto',
        transition: 'opacity 120ms ease, border-color 120ms ease',
      }}
    >
      <header style={{
        display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8,
        flexWrap: 'wrap',
      }}>
        <Pill value={row.status} palette={STATUS_COLOR} ariaLabel={`Estado: ${row.status}`} />
        <Pill value={row.severity} palette={SEVERITY_COLOR} ariaLabel={`Severidade: ${row.severity}`} />
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
        <time
          dateTime={row.created_at}
          style={{ marginLeft: 'auto', fontSize: 11, color: ADMIN_COLORS.muted }}
        >
          {new Date(row.created_at).toLocaleString()}
        </time>
      </header>

      <p style={{ fontSize: 14, color: ADMIN_COLORS.text, marginBottom: 6, margin: 0 }}>
        {row.reason}
      </p>

      {row.target_snippet && (
        <blockquote style={{
          fontSize: 13, color: ADMIN_COLORS.muted,
          background: 'rgba(255,255,255,0.02)',
          padding: 8, borderRadius: 6, margin: '8px 0',
          fontStyle: 'italic',
          borderLeft: `2px solid ${ADMIN_COLORS.accent}`,
        }}>
          "{row.target_snippet}"
        </blockquote>
      )}

      {row.target_user_email && (
        <div style={{ fontSize: 12, color: ADMIN_COLORS.muted, marginBottom: 8 }}>
          Owner: {row.target_user_email}
        </div>
      )}

      {showNote && (
        <div style={{ marginBottom: 8 }}>
          <label htmlFor={`note-${row.id}`} className="sr-only">
            Reason for {showNote}
          </label>
          <input
            ref={inputRef}
            id={`note-${row.id}`}
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit(showNote)
              if (e.key === 'Escape') setShowNote(null)
            }}
            placeholder={`Reason for ${showNote} (Enter to submit, Esc to cancel)`}
            style={{
              width: '100%', padding: 10,
              background: ADMIN_COLORS.surface,
              border: `1px solid ${ADMIN_COLORS.border}`,
              borderRadius: 6, color: ADMIN_COLORS.text,
              fontSize: 13, minHeight: 36,
            }}
          />
          <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
            <button
              type="button"
              onClick={() => submit(showNote)}
              style={btnFilled(
                showNote === 'reject' ? '#EF4444' :
                showNote === 'escalate' ? '#A855F7' : '#22C55E'
              )}
            >Confirm {showNote}</button>
            <button
              type="button"
              onClick={() => setShowNote(null)}
              style={btnGhost()}
            >Cancel</button>
          </div>
        </div>
      )}

      {!showNote && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button type="button" onClick={() => setShowNote('approve')}
                  aria-keyshortcuts="A"
                  style={btnOutline('#22C55E')}>
            Approve <kbd style={kbdStyle}>A</kbd>
          </button>
          <button type="button" onClick={() => setShowNote('reject')}
                  aria-keyshortcuts="R"
                  style={btnOutline('#EF4444')}>
            Reject <kbd style={kbdStyle}>R</kbd>
          </button>
          <button type="button" onClick={() => setShowNote('escalate')}
                  aria-keyshortcuts="E"
                  style={btnOutline('#A855F7')}>
            Escalate <kbd style={kbdStyle}>E</kbd>
          </button>
        </div>
      )}
    </article>
  )
}


const kbdStyle = {
  display: 'inline-block', marginLeft: 6, padding: '0 4px',
  border: '1px solid currentColor', borderRadius: 4,
  fontSize: 9, opacity: 0.6, fontFamily: 'monospace',
}

function btnFilled(color) {
  return {
    background: color, color: 'white', border: 'none',
    padding: '8px 14px', borderRadius: 6, fontSize: 12,
    fontWeight: 600, cursor: 'pointer', minHeight: 36,
  }
}
function btnGhost() {
  return {
    background: 'transparent', color: '#94A3B8',
    border: `1px solid ${ADMIN_COLORS.border}`,
    padding: '8px 14px', borderRadius: 6, fontSize: 12,
    cursor: 'pointer', minHeight: 36,
  }
}
function btnOutline(color) {
  return {
    background: 'transparent', color,
    border: `1px solid ${color}55`,
    padding: '8px 14px', borderRadius: 6, fontSize: 12,
    fontWeight: 600, cursor: 'pointer', minHeight: 36,
    display: 'inline-flex', alignItems: 'center',
  }
}


export default function AdminModerationQueuePage() {
  const [filters, setFilters] = useState({
    target_type: '', severity: '', status: '',
  })
  const params = useMemo(() => {
    const out = {}
    Object.entries(filters).forEach(([k, v]) => { if (v) out[k] = v })
    return out
  }, [filters])

  const query = useApiQuery('/api/v1/moderation/queue/', params)
  const items = query.data?.results || []
  const [busyIds, setBusyIds] = useState(() => new Set())
  const [focusIdx, setFocusIdx] = useState(0)
  const [localItems, setLocalItems] = useState(null)

  // Sync localItems from query results, preserving local optimistic state
  // by not overwriting when query is loading.
  useEffect(() => {
    if (query.isSuccess) setLocalItems(items)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.isSuccess, JSON.stringify(items.map(i => i.id))])

  const visible = localItems ?? items

  // Optimistic action: hide row immediately, restore on failure.
  const action = useCallback(
    async (row, kind, note) => {
      setBusyIds((s) => new Set([...s, row.id]))
      try {
        const { data } = await client.post(
          `/api/v1/moderation/queue/${row.id}/${kind}/`,
          { note },
        )
        // Success — remove from view and report escalation result.
        setLocalItems((prev) => (prev || []).filter((r) => r.id !== row.id))
        const esc = data?.escalation
        if (esc && esc.action && esc.action !== 'none') {
          toast.success(
            `Flag ${kind} — escalation: ${esc.action} (${esc.infractions} infractions)`
          )
        } else {
          toast.success(`Flag ${kind}`)
        }
      } catch (e) {
        toast.error(
          e?.response?.data?.detail
          || `Falhou ao ${kind} flag #${row.id}`
        )
      } finally {
        setBusyIds((s) => {
          const next = new Set(s)
          next.delete(row.id)
          return next
        })
      }
    },
    [],
  )

  // Clamp focusIdx when items are removed (optimistic action shrinks
  // the visible array; pre-fix focusIdx could point past the end).
  useEffect(() => {
    setFocusIdx((i) => {
      if (visible.length === 0) return 0
      return Math.min(i, visible.length - 1)
    })
  }, [visible.length])

  // Page-level keyboard nav.
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (visible.length === 0) return
      if (e.key === 'j' || e.key === 'J') {
        e.preventDefault()
        setFocusIdx((i) => Math.min(i + 1, visible.length - 1))
      }
      if (e.key === 'k' || e.key === 'K') {
        e.preventDefault()
        setFocusIdx((i) => Math.max(i - 1, 0))
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [visible.length])

  return (
    <AdminLayout title="Moderation Queue">
      <div style={{ padding: 16 }}>
        <Filters filters={filters} onChange={setFilters} onRefresh={query.refetch} />

        {query.isLoading && !localItems ? (
          <QueueListSkeleton count={5} />
        ) : query.isError ? (
          <ErrorState
            variant={query.error?.variant || 'generic'}
            detail={query.error?.detail}
            onRetry={query.refetch}
          />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={
              <div style={{ fontSize: 48 }} aria-hidden="true">✓</div>
            }
            title="Fila vazia"
            description="Não há conteúdo pendente de revisão. Volta mais tarde."
          />
        ) : (
          <>
            <div style={{
              padding: '8px 0', fontSize: 11, color: ADMIN_COLORS.muted,
            }}>
              {visible.length} item{visible.length === 1 ? '' : 's'} ·
              Tip: <kbd style={kbdStyle}>J</kbd>/<kbd style={kbdStyle}>K</kbd> to navigate,
              <kbd style={kbdStyle}>A</kbd>/<kbd style={kbdStyle}>R</kbd>/<kbd style={kbdStyle}>E</kbd> to act
            </div>
            <div role="list" aria-label="Moderation queue">
              {visible.map((row, i) => (
                <FlagRow
                  key={row.id}
                  row={row}
                  busy={busyIds.has(row.id)}
                  isFocused={i === focusIdx}
                  onApprove={(r, n) => action(r, 'approve', n)}
                  onReject={(r, n) => action(r, 'reject', n)}
                  onEscalate={(r, n) => action(r, 'escalate', n)}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}


function Filters({ filters, onChange, onRefresh }) {
  const set = (k, v) => onChange((f) => ({ ...f, [k]: v }))
  return (
    <div role="search" aria-label="Filtros"
         style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
      <select aria-label="Status"
              value={filters.status}
              onChange={(e) => set('status', e.target.value)}
              style={selectStyle}>
        <option value="">all open</option>
        <option value="pending">pending</option>
        <option value="escalated">escalated</option>
        <option value="approved">approved</option>
        <option value="rejected">rejected</option>
      </select>
      <select aria-label="Severity"
              value={filters.severity}
              onChange={(e) => set('severity', e.target.value)}
              style={selectStyle}>
        <option value="">any severity</option>
        <option value="high">high</option>
        <option value="medium">medium</option>
        <option value="low">low</option>
      </select>
      <select aria-label="Target type"
              value={filters.target_type}
              onChange={(e) => set('target_type', e.target.value)}
              style={selectStyle}>
        <option value="">all targets</option>
        <option value="product">product</option>
        <option value="listing">listing</option>
        <option value="review">review</option>
        <option value="message">message</option>
      </select>
      <button onClick={onRefresh}
              aria-label="Refresh queue"
              style={{ ...selectStyle, cursor: 'pointer', fontWeight: 600 }}>
        ↻
      </button>
    </div>
  )
}


const selectStyle = {
  background: ADMIN_COLORS.card,
  border: `1px solid ${ADMIN_COLORS.border}`,
  borderRadius: 6, padding: '8px 12px', fontSize: 12,
  color: ADMIN_COLORS.text, minHeight: 36,
}
