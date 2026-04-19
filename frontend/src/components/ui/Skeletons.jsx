// Shimmer animation base
const shimmer = `
  @keyframes shimmer {
    0%   { background-position: -400px 0; }
    100% { background-position: 400px 0; }
  }
`

const skeletonBg = {
  background: 'linear-gradient(90deg, #1E1E1E 25%, #2A2A2A 50%, #1E1E1E 75%)',
  backgroundSize: '800px 100%',
  animation: 'shimmer 1.4s ease-in-out infinite',
  borderRadius: 8,
}

function Block({ w = '100%', h = 16, r = 8, style = {} }) {
  return (
    <div style={{ ...skeletonBg, width: w, height: h, borderRadius: r, ...style }}>
      <style>{shimmer}</style>
    </div>
  )
}

// ── Product card skeleton ──────────────────────────────────────────────────
export function ProductCardSkeleton() {
  return (
    <div style={{ background: '#1E1E1E', borderRadius: 16, overflow: 'hidden', border: '1px solid #2A2A2A' }}>
      <Block h={180} r={0} />
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Block w="60%" h={10} />
        <Block w="85%" h={14} />
        <Block w="50%" h={14} />
        <Block w="40%" h={10} />
      </div>
    </div>
  )
}

// ── Home feed skeleton ─────────────────────────────────────────────────────
export function HomeSkeleton() {
  return (
    <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Search bar */}
      <Block h={48} r={14} />
      {/* Banner */}
      <Block h={160} r={20} />
      {/* Category pills */}
      <div style={{ display: 'flex', gap: 8 }}>
        {[80, 90, 100, 75, 85].map((w, i) => <Block key={i} w={w} h={36} r={50} />)}
      </div>
      {/* Product grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {[...Array(6)].map((_, i) => <ProductCardSkeleton key={i} />)}
      </div>
    </div>
  )
}

// ── Product detail skeleton ────────────────────────────────────────────────
export function ProductDetailSkeleton() {
  return (
    <div>
      <Block h={320} r={0} />
      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Block w="40%" h={12} />
        <Block w="80%" h={24} />
        <Block w="60%" h={24} />
        <Block h={1} />
        <Block h={60} r={14} />
        <Block h={120} r={14} />
      </div>
    </div>
  )
}

// ── Profile skeleton ───────────────────────────────────────────────────────
export function ProfileSkeleton() {
  return (
    <div>
      <div style={{ padding: '52px 20px 24px', display: 'flex', gap: 16 }}>
        <Block w={68} h={68} r="50%" style={{ flexShrink: 0 }} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, justifyContent: 'center' }}>
          <Block w="60%" h={20} />
          <Block w="80%" h={12} />
        </div>
      </div>
      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {[...Array(4)].map((_, i) => <Block key={i} h={56} r={14} />)}
      </div>
    </div>
  )
}

// ── Order list skeleton ────────────────────────────────────────────────────
export function OrderListSkeleton() {
  return (
    <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      {[...Array(4)].map((_, i) => (
        <div key={i} style={{ background: '#141414', borderRadius: 16, padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Block w="35%" h={14} />
            <Block w="20%" h={22} r={20} />
          </div>
          <Block w="55%" h={12} />
        </div>
      ))}
    </div>
  )
}

// ── Notification skeleton ──────────────────────────────────────────────────
export function NotificationSkeleton() {
  return (
    <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column' }}>
      {[...Array(5)].map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: 14, padding: '16px 0', borderBottom: '1px solid #141414' }}>
          <Block w={42} h={42} r={12} style={{ flexShrink: 0 }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Block w="70%" h={14} />
            <Block w="90%" h={12} />
          </div>
        </div>
      ))}
    </div>
  )
}
