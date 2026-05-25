/**
 * AdminAMLPage — production polish pass.
 */
import { useMemo, useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import { QueueListSkeleton } from '@/components/ui/AdminSkeletons'
import ConfirmSheet from '@/components/ui/ConfirmSheet'
import { useApiQuery } from '@/hooks/useApiKit'
import { toast } from '@/components/ui/Toast'
import client from '@/api/client'


const SEVERITY = {
  low:    '#4ADE80',
  medium: '#FBBF24',
  high:   '#F87171',
}


export default function AdminAMLPage() {
  const [filter, setFilter] = useState('open')
  const [reviewing, setReviewing] = useState(null)  // {alert, action}

  const params = useMemo(
    () => filter !== 'open' ? { status: filter } : {},
    [filter],
  )
  const query = useApiQuery('/api/v1/payments/aml/alerts/', params)
  const rows = query.data?.results || []

  const submit = async (action, note) => {
    if (!reviewing) return
    try {
      await client.post(
        `/api/v1/payments/aml/alerts/${reviewing.alert.id}/review/`,
        { action, note },
      )
      toast.success(action === 'report' ? 'STR filed' : 'Alert dismissed')
      query.refetch()
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed')
    } finally {
      setReviewing(null)
    }
  }

  return (
    <AdminLayout title="AML Alerts">
      <div style={{ padding: 16 }}>
        <div role="tablist" aria-label="Filter"
             style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {['open', 'under_review', 'reported', 'dismissed'].map(v => (
            <button key={v}
                    role="tab" aria-selected={filter === v}
                    onClick={() => setFilter(v)}
                    style={{
                      background: filter === v ? '#6366F1' : 'transparent',
                      color: filter === v ? 'white' : ADMIN_COLORS.text,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      padding: '8px 14px', borderRadius: 6,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      minHeight: 36,
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
            icon={<div style={{ fontSize: 48 }} aria-hidden>🛡️</div>}
            title="Sem alertas"
            description="Nenhum alerta AML neste filtro."
          />
        ) : rows.map(a => (
          <article key={a.id} aria-label={`AML alert ${a.id}`}
                   style={{
                     background: ADMIN_COLORS.card,
                     border: `1px solid ${ADMIN_COLORS.border}`,
                     borderRadius: 12, padding: 14, marginBottom: 12,
                   }}>
            <header style={{ display: 'flex', gap: 8, alignItems: 'center',
                             marginBottom: 6, flexWrap: 'wrap' }}>
              <span aria-label={`Severity: ${a.severity}`}
                    style={{
                      background: SEVERITY[a.severity] + '22',
                      color: SEVERITY[a.severity] || '#94A3B8',
                      padding: '3px 9px', borderRadius: 999,
                      fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                    }}>{a.severity}</span>
              <span style={{ fontSize: 12, color: ADMIN_COLORS.text }}>{a.kind}</span>
              <time dateTime={a.created_at}
                    style={{ marginLeft: 'auto', fontSize: 11, color: ADMIN_COLORS.muted }}>
                {new Date(a.created_at).toLocaleString()}
              </time>
            </header>
            <div style={{ fontSize: 14, color: ADMIN_COLORS.text, marginBottom: 6 }}>
              {a.aggregate_amount} AOA — {a.reason}
            </div>
            <div style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 10 }}>
              User: {a.user_email || a.user_id || '—'}
            </div>

            {a.status === 'open' && (
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={() => setReviewing({ alert: a, action: 'report' })}
                        style={{ ...btn, color: '#F87171', borderColor: '#F8717155' }}>
                  File STR
                </button>
                <button onClick={() => setReviewing({ alert: a, action: 'dismiss' })}
                        style={{ ...btn, color: '#94A3B8', borderColor: ADMIN_COLORS.border }}>
                  Dismiss
                </button>
              </div>
            )}
          </article>
        ))}
      </div>

      <ConfirmSheet
        open={!!reviewing}
        title="Review AML alert"
        description="Decide whether to file a Suspicious Transaction Report (STR) with the FIU or dismiss the alert as a false positive."
        noteLabel="Note"
        notePlaceholder="UIF-2026-001234, submitted via secure portal • or • Confirmed legitimate transaction…"
        initialActionId={reviewing?.action || 'report'}
        actions={[
          { id: 'report',  label: 'File STR', color: 'red' },
          { id: 'dismiss', label: 'Dismiss',  color: 'neutral', isPrimary: true },
        ]}
        onConfirm={(actionId, note) => submit(actionId, note)}
        onCancel={() => setReviewing(null)}
      />
    </AdminLayout>
  )
}


const btn = {
  background: 'transparent',
  padding: '8px 14px', border: '1px solid',
  borderRadius: 6, fontSize: 12, fontWeight: 600,
  cursor: 'pointer', minHeight: 36,
}
