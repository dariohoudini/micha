/**
 * AdminCommandCenterPage — Tier 5 unified ops dashboard.
 *
 * Single screen for incident response. Every widget pulls from a
 * backend we shipped earlier in this session:
 *
 *   • DLQ depth                 GET /api/v1/admin/outbox/dlq/        (R3)
 *   • Open AML alerts           GET /api/v1/payments/aml/alerts/     (R2)
 *   • Overdue chargebacks       GET /api/v1/payments/chargebacks/?overdue=1 (R2)
 *   • Moderator queue depth     GET /api/v1/moderation/queue/        (R4)
 *   • Settlement drift today    GET /api/v1/payments/settlement/runs/ (R2)
 *
 * Each widget click-through navigates to the relevant admin queue.
 * Auto-refreshes every 30s (admin-only, low traffic — cheap polling
 * beats websocket complexity for now).
 */
import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'
import { StatCardSkeleton } from '@/components/ui/AdminSkeletons'
import client from '@/api/client'


const REFRESH_MS = 30_000


function useWidget(path, params, mapper) {
  const [state, setState] = useState({ loading: true, data: null, error: null })

  const load = useCallback(async () => {
    try {
      const { data } = await client.get(path, { params })
      setState({ loading: false, data: mapper(data), error: null })
    } catch (e) {
      setState((s) => ({
        loading: false,
        data: s.data,  // keep stale on transient error
        error: e?.response?.data?.detail || e?.message || 'falhou',
      }))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, JSON.stringify(params)])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  return { ...state, refetch: load }
}


function Widget({ label, value, sub, accent = '#6366F1', onClick, loading, error }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: ADMIN_COLORS.card,
        border: `1px solid ${error ? 'rgba(239,68,68,0.4)' : ADMIN_COLORS.border}`,
        borderRadius: 12, padding: 16,
        flex: '1 1 220px', textAlign: 'left',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative', overflow: 'hidden',
        fontFamily: 'inherit', minHeight: 110,
      }}
    >
      <div style={{
        position: 'absolute', top: 0, left: 0, bottom: 0, width: 3,
        background: accent,
      }} />
      <div style={{
        fontSize: 11, color: ADMIN_COLORS.muted,
        textTransform: 'uppercase', letterSpacing: '0.06em',
        marginBottom: 8,
      }}>
        {label}
      </div>
      {loading ? (
        <div style={{ height: 28 }}>
          <div style={{
            height: 24, width: 60, borderRadius: 4,
            background: 'linear-gradient(90deg, #1A1A2E 25%, #2A2A3E 50%, #1A1A2E 75%)',
            backgroundSize: '200% 100%',
            animation: 'cc-shimmer 1.4s ease infinite',
          }} />
          <style>{`@keyframes cc-shimmer { 0%{background-position:-200% 0;} 100%{background-position:200% 0;} }`}</style>
        </div>
      ) : (
        <>
          <div style={{ fontSize: 26, fontWeight: 700, color: ADMIN_COLORS.text }}>
            {value}
          </div>
          {sub && (
            <div style={{ fontSize: 11, color: error ? '#F87171' : ADMIN_COLORS.muted, marginTop: 6 }}>
              {error ? `${error} (stale)` : sub}
            </div>
          )}
        </>
      )}
    </button>
  )
}


export default function AdminCommandCenterPage() {
  const navigate = useNavigate()

  const moderation = useWidget(
    '/api/v1/moderation/queue/',
    {},
    (d) => ({ count: d?.count || (d?.results?.length || 0) }),
  )
  const aml = useWidget(
    '/api/v1/payments/aml/alerts/',
    { status: 'open' },
    (d) => ({ count: d?.count || (d?.results?.length || 0) }),
  )
  const chargebacks = useWidget(
    '/api/v1/payments/chargebacks/',
    { overdue: 1 },
    (d) => ({ count: d?.count || (d?.results?.length || 0) }),
  )
  const settlement = useWidget(
    '/api/v1/payments/settlement/runs/',
    {},
    (d) => {
      const runs = d?.results || []
      const latest = runs[0]
      return {
        latest_date: latest?.settlement_date || null,
        total_drift: latest?.total_drift || '0',
        drift_rows: latest?.drift_rows || 0,
      }
    },
  )
  const realtime = useWidget(
    '/api/v1/analytics/admin/realtime/',
    {},
    (d) => ({
      orders_today: d?.orders_today || 0,
      revenue_today: d?.revenue_today || '0',
      pending_orders: d?.pending_orders || 0,
    }),
  )

  return (
    <AdminLayout title="Command Center">
      <div style={{ padding: 16 }}>
        <h2 style={{
          color: ADMIN_COLORS.text, fontSize: 14, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '0.06em',
          margin: '0 0 12px',
        }}>
          Live Operations
        </h2>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
          <Widget
            label="Pedidos Hoje"
            value={realtime.data?.orders_today ?? '—'}
            sub={`${Number(realtime.data?.revenue_today || 0).toLocaleString('pt-AO')} Kz`}
            accent="#22C55E"
            loading={realtime.loading && !realtime.data}
            error={realtime.error}
            onClick={() => navigate('/admin/orders')}
          />
          <Widget
            label="Pedidos Pendentes"
            value={realtime.data?.pending_orders ?? '—'}
            sub="Aguardam acção do vendedor"
            accent="#FBBF24"
            loading={realtime.loading && !realtime.data}
            error={realtime.error}
            onClick={() => navigate('/admin/orders?status=pending')}
          />
          <Widget
            label="Fila Moderação"
            value={moderation.data?.count ?? '—'}
            sub="Pendentes + escalados"
            accent="#A855F7"
            loading={moderation.loading && !moderation.data}
            error={moderation.error}
            onClick={() => navigate('/admin/moderation')}
          />
          <Widget
            label="Alertas AML"
            value={aml.data?.count ?? '—'}
            sub="Abertos — requerem revisão"
            accent="#F87171"
            loading={aml.loading && !aml.data}
            error={aml.error}
            onClick={() => navigate('/admin/aml')}
          />
          <Widget
            label="Chargebacks Atrasados"
            value={chargebacks.data?.count ?? '—'}
            sub="Prazo de evidência vencido"
            accent="#EF4444"
            loading={chargebacks.loading && !chargebacks.data}
            error={chargebacks.error}
            onClick={() => navigate('/admin/chargebacks?filter=overdue')}
          />
          <Widget
            label="Drift Settlement"
            value={
              settlement.data
                ? `${Number(settlement.data.total_drift || 0).toLocaleString('pt-AO')} Kz`
                : '—'
            }
            sub={
              settlement.data?.latest_date
                ? `${settlement.data.drift_rows} linhas · ${settlement.data.latest_date}`
                : 'Sem dados'
            }
            accent="#6366F1"
            loading={settlement.loading && !settlement.data}
            error={settlement.error}
            onClick={() => navigate('/admin/settlement')}
          />
        </div>

        <h2 style={{
          color: ADMIN_COLORS.text, fontSize: 14, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '0.06em',
          margin: '0 0 12px',
        }}>
          Acções Rápidas
        </h2>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <QuickActionButton
            label="Suspender utilizador"
            onClick={() => navigate('/admin/users?action=suspend')}
          />
          <QuickActionButton
            label="Reembolsar pedido"
            onClick={() => navigate('/admin/orders?action=refund')}
          />
          <QuickActionButton
            label="Aprovar verificação"
            onClick={() => navigate('/admin/sellers?status=pending_verification')}
          />
          <QuickActionButton
            label="Pagamentos"
            onClick={() => navigate('/admin/monitoring')}
          />
        </div>

        <p style={{
          color: ADMIN_COLORS.muted, fontSize: 11,
          marginTop: 24, textAlign: 'center',
        }}>
          Auto-actualiza a cada 30s
        </p>
      </div>
    </AdminLayout>
  )
}


function QuickActionButton({ label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: ADMIN_COLORS.card,
        border: `1px solid ${ADMIN_COLORS.border}`,
        color: ADMIN_COLORS.text,
        padding: '10px 16px', borderRadius: 8,
        fontSize: 12, fontWeight: 600,
        cursor: 'pointer', minHeight: 36,
        fontFamily: 'inherit',
      }}
    >
      {label}
    </button>
  )
}
