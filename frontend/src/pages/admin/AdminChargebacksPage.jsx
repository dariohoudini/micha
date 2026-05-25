/**
 * AdminChargebacksPage — production polish pass.
 *
 * Skeleton + EmptyState + ErrorState. Confirmation modal replaces
 * raw prompt() for note collection. Action toasts.
 */
import { useCallback, useMemo, useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import { QueueListSkeleton } from '@/components/ui/AdminSkeletons'
import ConfirmSheet from '@/components/ui/ConfirmSheet'
import { useApiQuery } from '@/hooks/useApiKit'
import { toast } from '@/components/ui/Toast'
import client from '@/api/client'


const STATUS_COLOR = {
  received: { bg: 'rgba(239,68,68,0.15)',  fg: '#F87171' },
  evidence: { bg: 'rgba(245,158,11,0.12)', fg: '#FBBF24' },
  won:      { bg: 'rgba(34,197,94,0.12)',  fg: '#4ADE80' },
  lost:     { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' },
  accepted: { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' },
}


function Pill({ value, ariaLabel }) {
  const c = STATUS_COLOR[value] || { bg: 'rgba(148,163,184,0.12)', fg: '#94A3B8' }
  return (
    <span aria-label={ariaLabel || value} style={{
      background: c.bg, color: c.fg,
      padding: '3px 9px', borderRadius: 999,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
    }}>{value}</span>
  )
}


function ChargebackRow({ row, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)
  // dialog: {title, noteLabel, placeholder, confirmLabel, color,
  //          onSubmit: (note) => Promise}

  const act = async (path, body) => {
    setBusy(true)
    try {
      const { data } = await client.post(
        `/api/v1/payments/chargebacks/${row.id}/${path}/`, body,
      )
      toast.success(`Chargeback ${data.status}`)
      onChanged?.(data)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falhou')
    } finally {
      setBusy(false)
      setDialog(null)
    }
  }

  const isTerminal = ['won', 'lost', 'accepted'].includes(row.status)
  const due = row.deadline_at && new Date(row.deadline_at)
  const overdue = row.overdue

  return (
    <>
      <article aria-label={`Chargeback case ${row.external_case_id}`}
               style={{
                 background: ADMIN_COLORS.card,
                 border: `1px solid ${overdue ? '#EF4444' : ADMIN_COLORS.border}`,
                 borderRadius: 12, padding: 14, marginBottom: 12,
                 opacity: busy ? 0.6 : 1,
                 transition: 'opacity 120ms ease',
               }}>
        <header style={{ display: 'flex', gap: 8, alignItems: 'center',
                         marginBottom: 8, flexWrap: 'wrap' }}>
          <Pill value={row.status} ariaLabel={`Status: ${row.status}`} />
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
          {due && (
            <time dateTime={row.deadline_at}
                  style={{ marginLeft: 'auto', fontSize: 11, color: ADMIN_COLORS.muted }}>
              Due {due.toLocaleDateString()}
            </time>
          )}
        </header>

        <div style={{ fontSize: 16, color: ADMIN_COLORS.text, marginBottom: 4 }}>
          {row.amount} {row.currency} — {row.reason_code}
        </div>

        {row.reason_text && (
          <p style={{ fontSize: 13, color: ADMIN_COLORS.muted, marginBottom: 8,
                      margin: '0 0 8px 0' }}>
            {row.reason_text}
          </p>
        )}

        <div style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 10 }}>
          Order: {row.order_id || '—'} | Payment: {row.payment_id || '—'}
        </div>

        {!isTerminal && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {row.status === 'received' && (
              <>
                <button onClick={() => setDialog({
                  title: 'Submit evidence',
                  noteLabel: 'Evidence summary (will be sent to issuer)',
                  placeholder: 'Tracking number, delivery confirmation, buyer chat refs…',
                  color: 'green', confirmLabel: 'Submit',
                  onSubmit: (note) => act('respond', { evidence: { admin_note: note } }),
                })} disabled={busy} style={btn('#22C55E')}>
                  Submit Evidence
                </button>
                <button onClick={() => setDialog({
                  title: 'Accept loss',
                  noteLabel: 'Reason (internal note)',
                  placeholder: 'Cheaper to accept than fight…',
                  color: 'neutral', confirmLabel: 'Accept loss',
                  onSubmit: (note) => act('accept', { note }),
                })} disabled={busy} style={btn('#94A3B8')}>
                  Accept Loss
                </button>
              </>
            )}
            {row.status === 'evidence' && (
              <>
                <button onClick={() => setDialog({
                  title: 'Mark as won',
                  noteLabel: 'Resolution note',
                  placeholder: 'Issuer ruled in our favour…',
                  color: 'green', confirmLabel: 'Won',
                  onSubmit: (note) => act('resolve', { won: true, note }),
                })} disabled={busy} style={btn('#22C55E')}>
                  Mark Won
                </button>
                <button onClick={() => setDialog({
                  title: 'Mark as lost',
                  noteLabel: 'Resolution note',
                  placeholder: 'Funds reversed…',
                  color: 'red', confirmLabel: 'Lost',
                  onSubmit: (note) => act('resolve', { won: false, note }),
                })} disabled={busy} style={btn('#EF4444')}>
                  Mark Lost
                </button>
              </>
            )}
          </div>
        )}
      </article>

      <ConfirmSheet
        open={!!dialog}
        title={dialog?.title || ''}
        noteLabel={dialog?.noteLabel || 'Note'}
        notePlaceholder={dialog?.placeholder || ''}
        actions={dialog ? [
          { id: 'confirm', label: dialog.confirmLabel || 'Confirm',
            color: dialog.color || 'indigo', isPrimary: true },
        ] : []}
        busy={busy}
        onConfirm={(_, note) => dialog?.onSubmit?.(note)}
        onCancel={() => setDialog(null)}
      />
    </>
  )
}


function btn(color) {
  return {
    background: 'transparent', color,
    border: `1px solid ${color}55`,
    padding: '8px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600,
    cursor: 'pointer', minHeight: 36,
  }
}


export default function AdminChargebacksPage() {
  const [filter, setFilter] = useState('open')

  const params = useMemo(() => {
    if (filter === 'overdue') return { overdue: 1 }
    if (filter === 'all') return {}
    return { status: 'received' }
  }, [filter])

  const query = useApiQuery('/api/v1/payments/chargebacks/', params)
  const rows = query.data?.results || []

  return (
    <AdminLayout title="Chargebacks">
      <div style={{ padding: 16 }}>
        <div role="tablist" aria-label="Filter" style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {['open', 'overdue', 'all'].map(v => (
            <button key={v}
                    role="tab" aria-selected={filter === v}
                    onClick={() => setFilter(v)}
                    style={{
                      background: filter === v ? '#6366F1' : 'transparent',
                      color: filter === v ? 'white' : ADMIN_COLORS.text,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      padding: '8px 14px', borderRadius: 6,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      textTransform: 'capitalize', minHeight: 36,
                    }}>{v}</button>
          ))}
        </div>

        {query.isLoading ? (
          <QueueListSkeleton count={4} />
        ) : query.isError ? (
          <ErrorState
            variant={query.error?.variant || 'generic'}
            detail={query.error?.detail}
            onRetry={query.refetch}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<div style={{ fontSize: 48 }} aria-hidden>💳</div>}
            title="Sem chargebacks"
            description={
              filter === 'overdue'
              ? 'Nenhum chargeback atrasado. Bom trabalho.'
              : 'Nada para revisão neste filtro.'
            }
          />
        ) : (
          rows.map(r => (
            <ChargebackRow key={r.id} row={r} onChanged={() => query.refetch()} />
          ))
        )}
      </div>
    </AdminLayout>
  )
}
