/**
 * src/components/VerificationGuard.jsx
 *
 * Wraps the entire seller section of the app.
 * If seller is not verified / locked / expired, shows the verification gate
 * instead of the normal app — total lockout as required.
 *
 * Usage in App.jsx:
 *   <Route path="/seller/*" element={
 *     <VerificationGuard>
 *       <SellerRoutes />
 *     </VerificationGuard>
 *   } />
 */
import { useState, useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import VerificationGatePage from '@/pages/verification/VerificationGatePage'
import MonthlySelfieGatePage from '@/pages/verification/MonthlySelfieGatePage'
import client from '@/api/client'

export default function VerificationGuard({ children }) {
  const { user, isSeller } = useAuthStore()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isSeller) {
      setLoading(false)
      return
    }
    checkVerificationStatus()
  }, [isSeller])

  const checkVerificationStatus = async () => {
    try {
      const res = await client.get('/api/verification-gate/status/')
      setStatus(res.data)
    } catch (err) {
      // If 403, the middleware already blocked — extract status from error
      if (err.response?.data?.status) {
        setStatus(err.response.data)
      } else {
        setStatus({ status: 'not_submitted', is_active: false })
      }
    } finally {
      setLoading(false)
    }
  }

  // Non-sellers pass through freely
  if (!isSeller) return children

  if (loading) return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', border: '3px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </div>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>A verificar identidade...</p>
      </div>
    </div>
  )

  if (!status) return children

  // ── Active and verified — allow through ────────────────────────────────────
  if (status.is_active) {
    // Show monthly selfie reminder banner if due soon (non-blocking)
    return children
  }

  // ── Monthly selfie overdue — show selfie gate ──────────────────────────────
  if (status.status === 'locked' && status.lock_reason === 'selfie_overdue') {
    return (
      <MonthlySelfieGatePage
        onComplete={checkVerificationStatus}
      />
    )
  }

  // ── All other states — show full verification gate ─────────────────────────
  return (
    <VerificationGatePage
      lockReason={status.lock_reason}
      rejectionReason={status.rejection_reason}
      rejectionNotes={status.rejection_notes}
      onComplete={checkVerificationStatus}
    />
  )
}
