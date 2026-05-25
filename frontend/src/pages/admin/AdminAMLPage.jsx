/**
 * AdminAMLPage — AML alert queue (R2).
 *   GET  /api/v1/payments/aml/alerts/
 *   POST .../alerts/<id>/review/   {action: 'report'|'dismiss', note}
 */
import { useCallback, useEffect, useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import client from '@/api/client'


const SEVERITY = {
  low:    '#4ADE80',
  medium: '#FBBF24',
  high:   '#F87171',
}


export default function AdminAMLPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('open')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = filter !== 'open' ? { status: filter } : {}
      const { data } = await client.get('/api/v1/payments/aml/alerts/', { params })
      setRows(data?.results || [])
    } catch { setRows([]) }
    finally { setLoading(false) }
  }, [filter])

  useEffect(() => { load() }, [load])

  const review = async (id, action) => {
    const note = prompt(`${action} note (STR reference if reporting)?`) || ''
    try {
      await client.post(`/api/v1/payments/aml/alerts/${id}/review/`, { action, note })
      load()
    } catch (e) {
      alert(e?.response?.data?.detail || 'Failed')
    }
  }

  return (
    <AdminLayout title="AML Alerts">
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {['open', 'under_review', 'reported', 'dismissed'].map(v => (
            <button key={v}
                    onClick={() => setFilter(v)}
                    style={{
                      background: filter === v ? '#6366F1' : 'transparent',
                      color: filter === v ? 'white' : ADMIN_COLORS.text,
                      border: `1px solid ${ADMIN_COLORS.border}`,
                      padding: '6px 14px', borderRadius: 6,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    }}>{v}</button>
          ))}
        </div>

        {loading ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20 }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div style={{ color: ADMIN_COLORS.muted, padding: 20, textAlign: 'center' }}>
            No alerts in this view.
          </div>
        ) : rows.map(a => (
          <div key={a.id} style={{
            background: ADMIN_COLORS.card,
            border: `1px solid ${ADMIN_COLORS.border}`,
            borderRadius: 12, padding: 14, marginBottom: 12,
          }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
              <span style={{
                background: SEVERITY[a.severity] + '22',
                color: SEVERITY[a.severity] || '#94A3B8',
                padding: '3px 9px', borderRadius: 999,
                fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
              }}>{a.severity}</span>
              <span style={{ fontSize: 12, color: ADMIN_COLORS.text }}>
                {a.kind}
              </span>
              <span style={{ marginLeft: 'auto', fontSize: 11, color: ADMIN_COLORS.muted }}>
                {new Date(a.created_at).toLocaleString()}
              </span>
            </div>
            <div style={{ fontSize: 14, color: ADMIN_COLORS.text, marginBottom: 6 }}>
              {a.aggregate_amount} AOA — {a.reason}
            </div>
            <div style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 10 }}>
              User: {a.user_email || a.user_id || '—'}
            </div>

            {a.status === 'open' && (
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={() => review(a.id, 'report')}
                        style={{ ...btn, color: '#F87171', borderColor: '#F8717155' }}>
                  File STR (Report to FIU)
                </button>
                <button onClick={() => review(a.id, 'dismiss')}
                        style={{ ...btn, color: '#94A3B8', borderColor: ADMIN_COLORS.border }}>
                  Dismiss (False Positive)
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </AdminLayout>
  )
}

const btn = {
  background: 'transparent', padding: '6px 14px',
  border: '1px solid', borderRadius: 6, fontSize: 12, fontWeight: 600,
  cursor: 'pointer',
}
