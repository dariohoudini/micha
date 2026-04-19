/**
 * Skeleton Loaders — MICHA Express
 * Shows while data is being fetched.
 * Better UX than spinners for content-heavy screens.
 */

const shimmerStyle = {
  background: 'linear-gradient(90deg, #1E1E1E 25%, #2A2A2A 50%, #1E1E1E 75%)',
  backgroundSize: '200% 100%',
  animation: 'skeleton-shimmer 1.4s ease infinite',
  borderRadius: 8,
}

export function SkeletonBox({ width = '100%', height = 16, radius = 8, style = {} }) {
  return (
    <div style={{ ...shimmerStyle, width, height, borderRadius: radius, ...style }}>
      <style>{`
        @keyframes skeleton-shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
      `}</style>
    </div>
  )
}

export function ProductCardSkeleton() {
  return (
    <div style={{ background: '#1E1E1E', borderRadius: 16, overflow: 'hidden', border: '1px solid #2A2A2A' }}>
      <SkeletonBox height={180} radius={0} />
      <div style={{ padding: '12px 12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <SkeletonBox height={10} width="40%" />
        <SkeletonBox height={13} width="90%" />
        <SkeletonBox height={13} width="70%" />
        <SkeletonBox height={16} width="55%" />
      </div>
    </div>
  )
}

export function ProductGridSkeleton({ count = 6 }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '0 16px' }}>
      {Array.from({ length: count }).map((_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  )
}

export function BannerSkeleton() {
  return (
    <div style={{ padding: '0 16px' }}>
      <SkeletonBox height={160} radius={20} />
    </div>
  )
}

export function CategorySkeleton() {
  return (
    <div style={{ display: 'flex', gap: 8, padding: '0 16px', overflow: 'hidden' }}>
      {[80, 90, 100, 80, 110].map((w, i) => (
        <SkeletonBox key={i} width={w} height={36} radius={50} style={{ flexShrink: 0 }} />
      ))}
    </div>
  )
}

export function HomeSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingBottom: 20 }}>
      {/* Search bar */}
      <div style={{ padding: '0 16px' }}>
        <SkeletonBox height={46} radius={14} />
      </div>
      <BannerSkeleton />
      <CategorySkeleton />
      {/* Section header */}
      <div style={{ padding: '0 16px', display: 'flex', justifyContent: 'space-between' }}>
        <SkeletonBox width={120} height={18} />
        <SkeletonBox width={60} height={14} />
      </div>
      <ProductGridSkeleton count={6} />
    </div>
  )
}

export function ProfileSkeleton() {
  return (
    <div style={{ padding: '52px 16px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        <SkeletonBox width={68} height={68} radius="50%" />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <SkeletonBox width="60%" height={20} />
          <SkeletonBox width="80%" height={13} />
        </div>
      </div>
      <SkeletonBox height={72} radius={14} style={{ marginBottom: 20 }} />
      {[1, 2, 3].map(i => (
        <SkeletonBox key={i} height={52} radius={12} style={{ marginBottom: 10 }} />
      ))}
    </div>
  )
}

export function OrderCardSkeleton() {
  return (
    <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <SkeletonBox width={120} height={14} />
        <SkeletonBox width={80} height={22} radius={20} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <SkeletonBox width="60%" height={13} />
        <SkeletonBox width={80} height={14} />
      </div>
    </div>
  )
}
