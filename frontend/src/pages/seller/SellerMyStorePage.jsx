import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

/**
 * SellerMyStorePage — /seller/store
 *
 * Mobile-adapted version of the AliExpress §7.2 "Application Status"
 * + §8.1 "Seller Dashboard" patterns from the process-flow spec.
 *
 * Purpose
 * ───────
 * When a seller finishes the SellerSetupPage Save flow, the docx
 * mandates the very next screen be one where they can SEE the store
 * they just created — name, banner, status, and CTAs to add a
 * product / edit the store / view the public listing. Before this
 * page existed, the post-save navigation dropped sellers on the
 * generic dashboard, which doesn't surface the store object — so
 * "I created a store but can't see it" was the user's literal
 * complaint.
 *
 * Behaviours specified by the docx that this page implements:
 *  • Big confirmation banner when the seller just saved (uses
 *    location.state.justSaved — set by SellerSetupPage).
 *  • Store identity card: banner image, logo, name, city.
 *  • Status badge: Approved / Pending / Inactive — maps to the
 *    Store.is_active / SellerProfile review state.
 *  • Three primary CTAs (AliExpress §8.2):
 *      [+ Adicionar Produto]   →  /seller/products/new
 *      [✎ Editar Loja]         →  /seller/setup
 *      [👁 Ver Loja Pública]    →  /store/<id>  (buyer view)
 *  • Empty state when no store yet — pushes seller into the setup
 *    wizard. This is the AliExpress §8.2 Option B "Start selling!"
 *    onboarding card, sized for mobile.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

function StatusBadge({ isActive, isOpen }) {
  // Approved + Open = green, Approved + Closed = amber, Pending = grey
  const cfg = !isActive
    ? { label: 'Inactiva', color: '#9A9A9A', bg: 'rgba(154,154,154,0.12)' }
    : isOpen
      ? { label: 'Activa', color: '#10b981', bg: 'rgba(16,185,129,0.12)' }
      : { label: 'Fechada', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', borderRadius: 20,
      background: cfg.bg, color: cfg.color,
      ...S, fontSize: 11, fontWeight: 700,
      letterSpacing: '0.04em',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.color }} />
      {cfg.label}
    </span>
  )
}

function CTAButton({ label, sub, icon, onClick, primary = false }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 14,
        padding: '14px 16px', borderRadius: 14,
        background: primary ? '#C9A84C' : '#141414',
        border: primary ? 'none' : '1px solid #1E1E1E',
        cursor: 'pointer', textAlign: 'left',
      }}
    >
      <div style={{
        width: 38, height: 38, borderRadius: 10,
        background: primary ? 'rgba(10,10,10,0.12)' : '#1E1E1E',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke={primary ? '#0A0A0A' : '#C9A84C'} strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round">
          <path d={icon} />
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ ...S, fontSize: 14, fontWeight: 600, color: primary ? '#0A0A0A' : '#FFFFFF' }}>{label}</p>
        {sub && <p style={{ ...S, fontSize: 11, color: primary ? 'rgba(10,10,10,0.7)' : '#9A9A9A', marginTop: 2 }}>{sub}</p>}
      </div>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke={primary ? '#0A0A0A' : '#555'} strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 18l6-6-6-6" />
      </svg>
    </button>
  )
}

export default function SellerMyStorePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [store, setStore] = useState(null)
  const [productsCount, setProductsCount] = useState(0)
  const [loading, setLoading] = useState(true)
  // Surface a transient "Loja criada!" confirmation when arriving
  // straight from a successful SellerSetupPage save.
  const [showJustSaved, setShowJustSaved] = useState(
    Boolean(location.state?.justSaved)
  )

  useEffect(() => {
    if (!showJustSaved) return
    const t = setTimeout(() => setShowJustSaved(false), 3500)
    return () => clearTimeout(t)
  }, [showJustSaved])

  // KYC status surfaces the AliExpress §7.2 application banner on
  // this screen so sellers know whether they're approved, awaiting
  // review, or still need to submit documents — without leaving the
  // "Minha Loja" landing.
  const [kyc, setKyc] = useState(null)

  useEffect(() => {
    Promise.allSettled([
      client.get('/api/v1/stores/my/'),
      client.get('/api/v1/products/my/?limit=1'),
      client.get('/api/v1/verification/status/').catch(() => null),
    ]).then(([storesRes, productsRes, kycRes]) => {
      if (storesRes.status === 'fulfilled') {
        const list = storesRes.value.data?.results || storesRes.value.data || []
        const first = Array.isArray(list) ? list[0] : list
        if (first && first.id) setStore(first)
      }
      if (productsRes.status === 'fulfilled') {
        const data = productsRes.value.data
        // The endpoint may return either a paginated envelope (count)
        // or a plain list — handle both so an API shape change
        // doesn't silently zero this out.
        setProductsCount(
          typeof data?.count === 'number'
            ? data.count
            : Array.isArray(data) ? data.length
            : (data?.results || []).length
        )
      }
      if (kycRes.status === 'fulfilled' && kycRes.value?.data) {
        setKyc(kycRes.value.data)
      }
    }).finally(() => setLoading(false))
  }, [])

  // ── Loading skeleton ─────────────────────────────────────────────
  if (loading) {
    return (
      <SellerLayout title="Minha Loja">
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ height: 180, borderRadius: 16, background: '#141414', animation: 'pulse 1.4s ease-in-out infinite' }} />
          <div style={{ height: 56, borderRadius: 12, background: '#141414', animation: 'pulse 1.4s ease-in-out infinite' }} />
          <div style={{ height: 56, borderRadius: 12, background: '#141414', animation: 'pulse 1.4s ease-in-out infinite' }} />
          <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.45} }`}</style>
        </div>
      </SellerLayout>
    )
  }

  // ── Empty state — no store yet ───────────────────────────────────
  if (!store) {
    return (
      <SellerLayout title="Minha Loja">
        <div style={{ padding: '32px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{
            background: 'linear-gradient(135deg, rgba(201,168,76,0.18), rgba(201,168,76,0.04))',
            border: '1px solid rgba(201,168,76,0.3)',
            borderRadius: 18, padding: 22,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(201,168,76,0.22)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10" />
                </svg>
              </div>
              <div>
                <p style={{ ...S, fontSize: 16, fontWeight: 700, color: '#FFFFFF' }}>Crie a sua loja</p>
                <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>Comece a vender em 2 minutos</p>
              </div>
            </div>
            <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 18 }}>
              Antes de publicar produtos, configure o nome, a descrição e
              o logótipo da sua loja. Pode editar a qualquer momento.
            </p>
            <button
              onClick={() => navigate('/seller/setup')}
              style={{
                width: '100%', padding: '14px 0', borderRadius: 12,
                border: 'none', background: '#C9A84C',
                ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A',
                cursor: 'pointer',
              }}
            >
              Criar a minha loja →
            </button>
          </div>
        </div>
      </SellerLayout>
    )
  }

  // ── Loaded — show the store ──────────────────────────────────────
  // Resolve banner: API may return either a relative MEDIA path or
  // an absolute URL depending on storage backend (local dev vs S3).
  const bannerSrc = store.banner_image
    ? (String(store.banner_image).startsWith('http')
        ? store.banner_image
        : `${client.defaults.baseURL || ''}${store.banner_image}`)
    : null

  return (
    <SellerLayout title="Minha Loja">
      {showJustSaved && (
        <div style={{
          position: 'fixed', top: 70, left: '50%', transform: 'translateX(-50%)',
          zIndex: 999, background: '#10b981', color: '#FFFFFF',
          padding: '10px 18px', borderRadius: 14,
          ...S, fontSize: 13, fontWeight: 600,
          boxShadow: '0 8px 24px rgba(16,185,129,0.35)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
          Loja guardada com sucesso!
        </div>
      )}

      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
        {/* AliExpress §7.2 application status banner — surfaces here
           so sellers always know whether they're approved, in
           review, or still need to submit. Tapping it jumps to the
           pipeline screen. */}
        {(!kyc || kyc.status !== 'approved') && (
          <button onClick={() => navigate(kyc ? '/seller/application' : '/seller/onboarding')}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '14px 16px', borderRadius: 14, cursor: 'pointer',
              textAlign: 'left', border: 'none',
              background: !kyc
                ? 'linear-gradient(135deg, rgba(245,158,11,0.18), rgba(245,158,11,0.04))'
                : kyc.status === 'rejected'
                  ? 'linear-gradient(135deg, rgba(239,68,68,0.18), rgba(239,68,68,0.04))'
                  : 'linear-gradient(135deg, rgba(99,102,241,0.18), rgba(99,102,241,0.04))',
              boxShadow: '0 0 0 1px rgba(255,255,255,0.04)',
            }}>
            <div style={{ width: 38, height: 38, borderRadius: 10, background: 'rgba(0,0,0,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              {!kyc ? '📋' : kyc.status === 'rejected' ? '⚠️' : '⏳'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ ...S, fontSize: 13, fontWeight: 700, color: '#FFFFFF' }}>
                {!kyc ? 'Complete a verificação para activar a loja'
                 : kyc.status === 'rejected' ? 'Aplicação rejeitada — toque para ver'
                 : 'Aplicação em revisão — toque para acompanhar'}
              </p>
              <p style={{ ...S, fontSize: 11, color: '#BFBFBF', marginTop: 2 }}>
                {!kyc ? 'KYC + conta bancária · 4 passos rápidos'
                 : kyc.status === 'rejected' ? 'Pode submeter novamente'
                 : 'Tempo médio: 1-3 dias úteis'}
              </p>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        )}

        {/* Store hero card — banner + name + status */}
        <div style={{
          borderRadius: 18, overflow: 'hidden',
          background: '#141414', border: '1px solid #1E1E1E',
        }}>
          <div style={{
            height: 140, position: 'relative',
            background: bannerSrc
              ? `url(${bannerSrc}) center/cover no-repeat`
              : `linear-gradient(135deg, ${store.primary_color || '#C9A84C'}, #0A0A0A)`,
          }}>
            {!bannerSrc && (
              <div style={{
                position: 'absolute', inset: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ ...S, fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                  Sem banner — adicione um na edição
                </span>
              </div>
            )}
          </div>
          <div style={{ padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h2 style={{ ...S, fontSize: 18, fontWeight: 700, color: '#FFFFFF', marginBottom: 4, wordBreak: 'break-word' }}>
                  {store.name}
                </h2>
                {store.city && (
                  <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>📍 {store.city}</p>
                )}
              </div>
              <StatusBadge isActive={store.is_active} isOpen={store.is_open} />
            </div>
            {store.description && (
              <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.55, marginTop: 10 }}>
                {store.description}
              </p>
            )}
          </div>
        </div>

        {/* Quick metrics row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          {[
            { label: 'Produtos', value: productsCount },
            { label: 'Avaliação', value: store.average_rating ? Number(store.average_rating).toFixed(1) : '—' },
            { label: 'Avaliações', value: store.total_reviews || 0 },
          ].map(m => (
            <div key={m.label} style={{
              background: '#141414', border: '1px solid #1E1E1E',
              borderRadius: 12, padding: '12px 8px', textAlign: 'center',
            }}>
              <p style={{ ...S, fontSize: 18, fontWeight: 700, color: '#C9A84C' }}>{m.value}</p>
              <p style={{ ...S, fontSize: 10, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: 2 }}>{m.label}</p>
            </div>
          ))}
        </div>

        {/* Primary CTAs — AliExpress §8.2 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <CTAButton
            primary
            label="Adicionar Produto"
            sub="Publique um novo produto na sua loja"
            icon="M12 5v14M5 12h14"
            onClick={() => navigate('/seller/products/new')}
          />
          <CTAButton
            label="Editar Loja"
            sub="Alterar nome, banner, descrição"
            icon="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
            onClick={() => navigate('/seller/setup')}
          />
          <CTAButton
            label="Ver Loja Pública"
            sub="Como os compradores vêem a sua loja"
            icon="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"
            onClick={() => navigate(`/store/${store.id}`)}
          />
          <CTAButton
            label="Meus Produtos"
            sub={productsCount === 0 ? 'Ainda não publicou produtos' : `${productsCount} produto(s) na loja`}
            icon="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"
            onClick={() => navigate('/seller/products')}
          />
          <CTAButton
            label="Centro de Vendedor"
            sub="KYC, banco, configuração completa"
            icon="M20 7L9 18l-5-5"
            onClick={() => navigate('/seller/onboarding')}
          />
        </div>
      </div>
    </SellerLayout>
  )
}
