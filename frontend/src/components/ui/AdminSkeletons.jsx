/**
 * Admin-area skeleton primitives.
 *
 * The admin pages have a distinct visual surface (dark, list/queue
 * heavy) that needs its own skeleton shapes. Reusing the shimmer
 * primitive from Skeleton.jsx so the animation is consistent.
 */
import { SkeletonBox } from './Skeleton'


const CARD_BG = '#111120'
const CARD_BORDER = '#1A1A2E'


export function QueueRowSkeleton() {
  return (
    <div style={{
      background: CARD_BG,
      border: `1px solid ${CARD_BORDER}`,
      borderRadius: 12, padding: 14, marginBottom: 12,
    }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <SkeletonBox width={60} height={18} radius={999} />
        <SkeletonBox width={50} height={18} radius={999} />
        <SkeletonBox width={90} height={12} style={{ marginLeft: 'auto' }} />
      </div>
      <SkeletonBox height={14} width="85%" style={{ marginBottom: 6 }} />
      <SkeletonBox height={12} width="60%" style={{ marginBottom: 12 }} />
      <div style={{ display: 'flex', gap: 6 }}>
        <SkeletonBox width={80} height={32} radius={6} />
        <SkeletonBox width={80} height={32} radius={6} />
        <SkeletonBox width={80} height={32} radius={6} />
      </div>
    </div>
  )
}


export function QueueListSkeleton({ count = 5 }) {
  return (
    <div role="status" aria-label="A carregar fila…">
      {Array.from({ length: count }).map((_, i) => (
        <QueueRowSkeleton key={i} />
      ))}
    </div>
  )
}


export function StatCardSkeleton() {
  return (
    <div style={{
      background: CARD_BG,
      border: `1px solid ${CARD_BORDER}`,
      borderRadius: 12, padding: 14, flex: '1 1 140px',
    }}>
      <SkeletonBox width={70} height={10} style={{ marginBottom: 8 }} />
      <SkeletonBox width={90} height={24} style={{ marginBottom: 6 }} />
      <SkeletonBox width={60} height={10} />
    </div>
  )
}


export function DashboardSkeleton() {
  return (
    <div role="status" aria-label="A carregar painel…" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
        {[7, 30, 90, 365].map(i => (
          <SkeletonBox key={i} width={50} height={32} radius={6} />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
      <ChartSkeleton />
      <ChartSkeleton height={200} />
    </div>
  )
}


export function ChartSkeleton({ height = 220 }) {
  return (
    <div style={{
      background: CARD_BG,
      border: `1px solid ${CARD_BORDER}`,
      borderRadius: 12, padding: 14, marginBottom: 12,
    }}>
      <SkeletonBox width={120} height={14} style={{ marginBottom: 12 }} />
      <SkeletonBox height={height} radius={6} />
    </div>
  )
}


export function TableRowSkeleton({ cols = 5 }) {
  return (
    <div style={{
      display: 'flex', gap: 12, alignItems: 'center',
      padding: '12px 14px',
      borderBottom: `1px solid ${CARD_BORDER}`,
    }}>
      {Array.from({ length: cols }).map((_, i) => (
        <SkeletonBox key={i} height={12} width={i === 0 ? '15%' : `${20 + i * 5}%`} />
      ))}
    </div>
  )
}


export function TableSkeleton({ rows = 6, cols = 5 }) {
  return (
    <div
      role="status"
      aria-label="A carregar tabela…"
      style={{
        background: CARD_BG, border: `1px solid ${CARD_BORDER}`,
        borderRadius: 12, overflow: 'hidden',
      }}
    >
      {Array.from({ length: rows }).map((_, i) => (
        <TableRowSkeleton key={i} cols={cols} />
      ))}
    </div>
  )
}
