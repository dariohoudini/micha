export default function PullToRefreshIndicator({ pullY, refreshing }) {
  const THRESHOLD = 70
  const progress = Math.min(pullY / THRESHOLD, 1)
  if (pullY === 0 && !refreshing) return null
  return (
    <div style={{
      position: 'fixed', top: 0, left: '50%', transform: 'translateX(-50%)',
      zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
      paddingTop: Math.min(pullY * 0.5, 40) + 'px',
      transition: refreshing ? 'none' : 'padding 0.1s',
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        background: '#1E1E1E', border: '1.5px solid #2A2A2A',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
      }}>
        {refreshing ? (
          <div style={{ width: 16, height: 16, border: '2px solid #C9A84C', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="#C9A84C" strokeWidth="2" strokeLinecap="round"
            style={{ transform: `rotate(${progress * 180}deg)`, transition: 'transform 0.1s' }}>
            <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/>
          </svg>
        )}
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}
