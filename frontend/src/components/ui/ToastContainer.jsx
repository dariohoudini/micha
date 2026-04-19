import { useUIStore } from '@/stores/uiStore'

const TYPE_CONFIG = {
  success: { bg: '#059669', border: 'rgba(5,150,105,0.3)', icon: 'M20 6L9 17l-5-5' },
  error:   { bg: '#dc2626', border: 'rgba(220,38,38,0.3)',  icon: 'M18 6L6 18M6 6l12 12' },
  warning: { bg: '#f59e0b', border: 'rgba(245,158,11,0.3)', icon: 'M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z' },
  info:    { bg: '#3b82f6', border: 'rgba(59,130,246,0.3)', icon: 'M12 16v-4M12 8h.01M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z' },
}

export default function ToastContainer() {
  const { toasts, dismissToast } = useUIStore()

  if (!toasts.length) return null

  return (
    <div style={{
      position: 'fixed',
      top: 'calc(env(safe-area-inset-top, 0px) + 16px)',
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      width: 'calc(100% - 32px)',
      maxWidth: 400,
      pointerEvents: 'none',
    }}>
      {toasts.map((toast) => {
        const config = TYPE_CONFIG[toast.type] || TYPE_CONFIG.info
        return (
          <div
            key={toast.id}
            onClick={() => dismissToast(toast.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '12px 16px', borderRadius: 14,
              background: '#1E1E1E',
              border: `1px solid ${config.border}`,
              boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
              pointerEvents: 'auto', cursor: 'pointer',
              animation: 'toastIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
            }}
          >
            <style>{`
              @keyframes toastIn {
                from { opacity: 0; transform: translateY(-12px) scale(0.95); }
                to   { opacity: 1; transform: translateY(0) scale(1); }
              }
            `}</style>

            {/* Icon */}
            <div style={{
              width: 28, height: 28, borderRadius: 8, flexShrink: 0,
              background: `${config.bg}20`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke={config.bg} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d={config.icon} />
              </svg>
            </div>

            <span style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 13, fontWeight: 500, color: '#FFFFFF',
              flex: 1, lineHeight: 1.4,
            }}>
              {toast.message}
            </span>

            {/* Progress bar */}
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0, height: 2,
              borderRadius: '0 0 14px 14px',
              background: config.bg,
              animation: `shrink ${toast.duration}ms linear forwards`,
            }} />
            <style>{`
              @keyframes shrink {
                from { width: 100%; }
                to   { width: 0%; }
              }
            `}</style>
          </div>
        )
      })}
    </div>
  )
}
