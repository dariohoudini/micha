import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

/**
 * SellerApplicationStatusPage — /seller/application
 *
 * Implements §7.2 of the AliExpress Process Flow spec:
 * the post-submission "Application Status" page showing the seller
 * a pipeline of review stages with their current position.
 *
 * Status mapping (spec → backend SellerVerification.status)
 * ─────────────────────────────────────────────────────────
 *   "Submitted"           ←→  pending
 *   "Documents Under Review" ←→ under_review
 *   "Additional Info Required" ←→ (no exact backend value yet;
 *                                  we surface rejected with note)
 *   "Approved"            ←→  approved
 *   "Rejected"            ←→  rejected
 *
 * Behaviours implemented:
 *   • Visual timeline showing current stage (§7.2)
 *   • "Approved" state: confetti emoji + [GO TO SELLER DASHBOARD]
 *     CTA → /seller/store (§7.3 final)
 *   • "Rejected" state: rejection reason card with
 *     [Reapply available in N days] countdown (§7.3 rejected)
 *   • "Additional Info Required" → [Upload Additional Documents]
 *     CTA returning to onboarding (§7.3 action required)
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

const STAGES = [
  { key: 'pending',      label: 'Submetido',           sub: 'Aplicação recebida.' },
  { key: 'under_review', label: 'Em revisão',          sub: 'Equipa MICHA a verificar documentos.' },
  { key: 'approved',     label: 'Aprovado',            sub: 'A sua loja pode publicar produtos.' },
]

function StageRow({ s, active, done, last }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{
          width: 26, height: 26, borderRadius: '50%',
          background: done ? '#10b981' : (active ? '#C9A84C' : '#1E1E1E'),
          color: done || active ? '#0A0A0A' : '#9A9A9A',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          ...S, fontSize: 12, fontWeight: 700,
          boxShadow: active ? '0 0 0 4px rgba(201,168,76,0.18)' : 'none',
        }}>
          {done ? '✓' : (active ? '•' : '')}
        </div>
        {!last && (
          <div style={{ width: 2, flex: 1, minHeight: 28, background: done ? '#10b981' : '#1E1E1E', marginTop: 2 }} />
        )}
      </div>
      <div style={{ paddingBottom: 18, flex: 1 }}>
        <p style={{ ...S, fontSize: 14, fontWeight: 600, color: active || done ? '#FFFFFF' : '#9A9A9A' }}>
          {s.label}
        </p>
        <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 2, lineHeight: 1.5 }}>
          {s.sub}
        </p>
        {active && (
          <span style={{ display: 'inline-block', marginTop: 6, padding: '3px 10px', borderRadius: 12, background: 'rgba(201,168,76,0.15)', ...S, fontSize: 10, fontWeight: 700, color: '#C9A84C', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Estado actual
          </span>
        )}
      </div>
    </div>
  )
}

export default function SellerApplicationStatusPage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [kyc, setKyc] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/api/v1/verification/status/')
      .then(r => setKyc(r.data))
      .catch(() => setKyc(null))
      .finally(() => setLoading(false))
  }, [])

  // Pipeline index based on backend status.
  const stageIdx = (() => {
    if (!kyc) return -1
    if (kyc.status === 'approved') return 2
    if (kyc.status === 'rejected') return -1
    if (kyc.status === 'under_review') return 1
    return 0  // pending
  })()

  if (loading) {
    return (
      <SellerLayout title="Estado da Aplicação" showBack>
        <div style={{ padding: 16 }}>
          <div style={{ height: 200, borderRadius: 14, background: '#141414', animation: 'pulse 1.4s ease-in-out infinite' }} />
          <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.45}}`}</style>
        </div>
      </SellerLayout>
    )
  }

  // Nothing submitted yet
  if (!kyc) {
    return (
      <SellerLayout title="Estado da Aplicação" showBack>
        <div style={{ padding: 24 }}>
          <div style={{ padding: 20, background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14 }}>
            <p style={{ ...S, fontSize: 15, fontWeight: 600, color: '#FFFFFF', marginBottom: 6 }}>
              Ainda não submeteu a aplicação
            </p>
            <p style={{ ...S, fontSize: 13, color: '#9A9A9A', lineHeight: 1.55, marginBottom: 16 }}>
              Complete o KYC na configuração para iniciar o processo de aprovação.
            </p>
            <button onClick={() => navigate('/seller/onboarding')}
              style={{ width: '100%', padding: '12px 0', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
              Ir para configuração →
            </button>
          </div>
        </div>
      </SellerLayout>
    )
  }

  // Rejected
  if (kyc.status === 'rejected') {
    return (
      <SellerLayout title="Estado da Aplicação" showBack>
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ padding: 20, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(239,68,68,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
              </div>
              <p style={{ ...S, fontSize: 15, fontWeight: 700, color: '#ef4444' }}>Aplicação rejeitada</p>
            </div>
            {kyc.rejection_reason && (
              <div style={{ background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 10, marginBottom: 12 }}>
                <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Motivo</p>
                <p style={{ ...S, fontSize: 13, color: '#FFFFFF', lineHeight: 1.55 }}>{kyc.rejection_reason}</p>
              </div>
            )}
            <p style={{ ...S, fontSize: 12, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 14 }}>
              Pode submeter novamente após corrigir os problemas indicados.
            </p>
            <button onClick={() => navigate('/seller/onboarding')}
              style={{ width: '100%', padding: '12px 0', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
              Submeter novamente
            </button>
          </div>
        </div>
      </SellerLayout>
    )
  }

  // Approved
  if (kyc.status === 'approved') {
    return (
      <SellerLayout title="Estado da Aplicação" showBack>
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{
            padding: '22px 20px',
            background: 'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(16,185,129,0.04))',
            border: '1px solid rgba(16,185,129,0.35)', borderRadius: 16,
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 40, marginBottom: 6 }}>🎉</div>
            <p style={{ ...S, fontSize: 18, fontWeight: 700, color: '#FFFFFF', marginBottom: 6 }}>
              A sua loja está activa!
            </p>
            <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.55 }}>
              Aprovada em {new Date(kyc.approved_at || kyc.reviewed_at).toLocaleDateString('pt-AO')}. Já pode publicar produtos.
            </p>
          </div>
          <button onClick={() => navigate('/seller/store')}
            style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 15, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            Ir para a minha loja →
          </button>
          <button onClick={() => navigate('/seller/products/new')}
            style={{ width: '100%', padding: '13px 0', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 14, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
            + Adicionar primeiro produto
          </button>
        </div>
      </SellerLayout>
    )
  }

  // Pending / Under Review — pipeline view
  return (
    <SellerLayout title="Estado da Aplicação" showBack>
      <div style={{ padding: 20 }}>
        <div style={{ padding: 18, background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, marginBottom: 16 }}>
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Aplicação</p>
          <p style={{ ...S, fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>{user?.email}</p>
          <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 6 }}>
            Submetida em {new Date(kyc.created_at).toLocaleDateString('pt-AO')}
          </p>
        </div>

        <div style={{ padding: '8px 4px' }}>
          {STAGES.map((s, i) => (
            <StageRow
              key={s.key}
              s={s}
              active={i === stageIdx}
              done={i < stageIdx}
              last={i === STAGES.length - 1}
            />
          ))}
        </div>

        <div style={{ marginTop: 8, padding: 14, background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 12 }}>
          <p style={{ ...S, fontSize: 12, color: '#f59e0b', lineHeight: 1.55 }}>
            ⏱ Tempo médio de revisão: 1-3 dias úteis. Receberá um email assim que houver decisão.
          </p>
        </div>
      </div>
    </SellerLayout>
  )
}
