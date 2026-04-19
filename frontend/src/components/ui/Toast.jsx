import { Toaster, toast as sonnerToast } from 'sonner'

/**
 * MICHA Toast System
 * Wraps Sonner with MICHA brand styling
 */

// Styled toast provider — add <ToastProvider /> to App root
export function ToastProvider() {
  return (
    <Toaster
      position="top-center"
      toastOptions={{
        style: {
          background: '#1E1E1E',
          border: '1px solid #2A2A2A',
          color: '#FFFFFF',
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '14px',
          borderRadius: '14px',
          padding: '12px 16px',
          maxWidth: '360px',
        },
        classNames: {
          success: 'toast-success',
          error: 'toast-error',
          warning: 'toast-warning',
        },
      }}
      offset={60}
      gap={8}
      richColors={false}
    />
  )
}

// Toast utilities
export const toast = {
  success: (message, options) => sonnerToast(message, {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    ),
    ...options,
  }),

  error: (message, options) => sonnerToast(message, {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="#dc2626" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
    ...options,
  }),

  info: (message, options) => sonnerToast(message, {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="#C9A84C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="8" />
        <line x1="12" y1="12" x2="12" y2="16" />
      </svg>
    ),
    ...options,
  }),

  loading: (message) => sonnerToast.loading(message, {
    style: {
      background: '#1E1E1E',
      border: '1px solid #2A2A2A',
      color: '#FFFFFF',
      fontFamily: "'DM Sans', sans-serif",
    },
  }),

  dismiss: sonnerToast.dismiss,
  promise: sonnerToast.promise,
}
