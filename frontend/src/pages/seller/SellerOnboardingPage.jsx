import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

/**
 * SellerOnboardingPage — /seller/onboarding
 *
 * Implements PART A of the AliExpress Process Flow spec — adapted
 * for mobile. The desktop spec has a left-rail wizard with 5 steps;
 * we use a vertical card-stack with progressive disclosure: each
 * card shows its state (Não iniciado / Em revisão / Concluído) and
 * expands when tapped.
 *
 * Stages (spec → screen):
 *   §3 Business Info   →  card 1 — full_name, address, phone, email
 *                          (most pulled from the user record; this
 *                          is light-touch confirmation)
 *   §4 KYC Documents   →  card 2 — id_number, id_doc, selfie upload
 *                          POSTs to existing /api/v1/verification/apply/
 *   §5 Store Setup     →  card 3 — links into /seller/setup wizard
 *                          (the dedicated screen we built earlier)
 *   §6 Bank Account    →  card 4 — bank name + account form
 *                          POSTs to /api/v1/payments/bank-accounts/
 *   §7 Review & Submit →  card 5 — application status badge + CTA
 *                          uses /api/v1/verification/status/ as the
 *                          authoritative go-live signal
 *
 * Skipped vs spec (out of scope for a single-turn build)
 * ──────────────────────────────────────────────────────
 *   • Browser camera liveness check (§4.4) — needs MediaDevices
 *     wiring & a backend liveness service
 *   • Payoneer OAuth (§6.2) — needs an OAuth integration
 *   • Country-specific business-licence validators (§3.2) — would
 *     need a country lookup table; we treat the form as Angola-only
 *
 * The submit-for-approval action triggers a real /verification/apply/
 * if not already done; if the seller's KYC was previously approved
 * we surface that, otherwise we show the §7.2 status pipeline.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }
const inputStyle = {
  width: '100%', background: '#0F0F0F', border: '1px solid #2A2A2A',
  borderRadius: 10, padding: '11px 13px', ...S, fontSize: 13,
  color: '#FFFFFF', outline: 'none', boxSizing: 'border-box',
}
const labelStyle = {
  ...S, fontSize: 10, color: '#9A9A9A', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.08em',
  marginBottom: 6, display: 'block',
}


// ── Step pill ──────────────────────────────────────────────────────
function StepStatus({ state }) {
  // state: 'todo' | 'progress' | 'done' | 'rejected'
  const cfg = {
    todo:     { label: 'Por fazer',  color: '#9A9A9A', bg: 'rgba(154,154,154,0.12)' },
    progress: { label: 'Em revisão', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    done:     { label: 'Completo',   color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    rejected: { label: 'Rejeitado',  color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
  }[state] || { label: state, color: '#9A9A9A', bg: '#1E1E1E' }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 9px', borderRadius: 12,
      background: cfg.bg, color: cfg.color,
      ...S, fontSize: 10, fontWeight: 700,
      letterSpacing: '0.04em', textTransform: 'uppercase',
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: cfg.color }} />
      {cfg.label}
    </span>
  )
}


// ── Generic collapsible step card ──────────────────────────────────
function StepCard({ number, title, subtitle, state, open, onToggle, children }) {
  return (
    <div style={{
      background: '#141414', border: '1px solid #1E1E1E',
      borderRadius: 14, overflow: 'hidden',
    }}>
      <button onClick={onToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 16px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: state === 'done' ? '#10b981' : (state === 'rejected' ? '#ef4444' : '#1E1E1E'),
          color: state === 'done' || state === 'rejected' ? '#FFFFFF' : '#9A9A9A',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          ...S, fontSize: 13, fontWeight: 700, flexShrink: 0,
        }}>{state === 'done' ? '✓' : state === 'rejected' ? '!' : number}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFFFFF' }}>{title}</p>
          {subtitle && <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{subtitle}</p>}
        </div>
        <StepStatus state={state} />
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div style={{ padding: '4px 16px 18px', borderTop: '1px solid #1E1E1E' }}>
          {children}
        </div>
      )}
    </div>
  )
}


// ── File-pick block — §4.3 with drag-drop ──────────────────────────
function FilePicker({ label, accept, file, onPick, hint }) {
  const ref = useRef()
  const [dragOver, setDragOver] = useState(false)
  const url = file ? (typeof file === 'string' ? file : URL.createObjectURL(file)) : null
  const isImage = !file || (typeof file !== 'string' && (file?.type || '').startsWith('image/'))
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => {
          e.preventDefault(); setDragOver(false)
          const f = e.dataTransfer?.files?.[0]
          if (f) onPick(f)
        }}
        onClick={() => ref.current?.click()}
        style={{
          width: '100%', minHeight: 92, borderRadius: 12,
          background: dragOver ? 'rgba(201,168,76,0.06)' : '#0F0F0F',
          border: `1.5px dashed ${file ? '#10b981' : dragOver ? '#C9A84C' : '#2A2A2A'}`,
          cursor: 'pointer', overflow: 'hidden', position: 'relative',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'all 0.15s',
        }}>
        {url && isImage ? (
          <img src={url} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover', maxHeight: 160, pointerEvents: 'none' }} />
        ) : url ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: 14 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
            <span style={{ ...S, fontSize: 11, color: '#10b981' }}>{file?.name || 'Documento carregado'}</span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
            <span style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{dragOver ? 'Solte aqui' : 'Carregar ou arrastar'}</span>
          </div>
        )}
      </div>
      {hint && <p style={{ ...S, fontSize: 10, color: '#555', marginTop: 4 }}>{hint}</p>}
      <input ref={ref} type="file" accept={accept} style={{ display: 'none' }}
        onChange={e => onPick(e.target.files?.[0] || null)} />
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// MAIN
// ════════════════════════════════════════════════════════════════════
export default function SellerOnboardingPage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [openStep, setOpenStep] = useState(null)
  const [toast, setToast] = useState(null)
  const [loading, setLoading] = useState(true)

  // Backend-loaded status flags
  const [hasStore, setHasStore] = useState(false)
  const [storeName, setStoreName] = useState('')
  const [kyc, setKyc] = useState(null)       // SellerVerification record
  const [bankAccts, setBankAccts] = useState([])

  // Local forms — KYC + bank form state
  // §3 Business Information Form — full set per spec.
  const [biz, setBiz] = useState({
    account_type: 'individual',  // individual | business
    full_name: '',
    legal_company_name: '',
    country: 'Angola',
    business_licence_number: '',
    incorporation_date: '',
    business_address: '',
    legal_rep_name: '',
    legal_rep_id_number: '',
    phone: '',
    email: '',
    website: '',
    annual_revenue: '',
    address: '',
  })
  const [kycForm, setKycForm] = useState({
    is_business_account: false,
    id_number: '', id_expiry_date: '',
    id_document: null, id_document_back: null, selfie: null,
    business_licence: null, bank_proof: null, power_of_attorney: null,
  })
  const [bankForm, setBankForm] = useState({
    bank_name: '', account_name: '', account_number: '', iban: '',
  })
  const [submitting, setSubmitting] = useState({})

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    Promise.allSettled([
      client.get('/api/v1/stores/my/'),
      client.get('/api/v1/verification/status/').catch(() => null),
      client.get('/api/v1/payments/bank-accounts/').catch(() => null),
    ]).then(([storesRes, kycRes, bankRes]) => {
      if (storesRes.status === 'fulfilled') {
        const list = storesRes.value.data?.results || storesRes.value.data || []
        const first = Array.isArray(list) ? list[0] : list
        if (first && first.id) { setHasStore(true); setStoreName(first.name) }
      }
      if (kycRes.status === 'fulfilled' && kycRes.value?.data) {
        setKyc(kycRes.value.data)
      }
      if (bankRes.status === 'fulfilled' && bankRes.value?.data) {
        const list = bankRes.value.data?.results || bankRes.value.data || []
        setBankAccts(Array.isArray(list) ? list : [])
      }
      // Prefill business info from user
      setBiz(b => ({
        ...b,
        full_name: user?.profile?.full_name || user?.username || '',
        phone: user?.phone || '',
        address: user?.profile?.address || '',
      }))
    }).finally(() => setLoading(false))
  }, [user])

  // ── Submit handlers ─────────────────────────────────────────────
  const submitBiz = async () => {
    const isBiz = biz.account_type === 'business'
    if (isBiz) {
      const req = ['legal_company_name', 'business_licence_number', 'incorporation_date', 'business_address', 'legal_rep_name', 'legal_rep_id_number']
      for (const k of req) {
        if (!(biz[k] || '').toString().trim()) { showToast(`Preencha: ${k.replaceAll('_', ' ')}.`, 'error'); return }
      }
    } else {
      if (!biz.full_name.trim()) { showToast('Preencha o nome legal completo.', 'error'); return }
    }
    if (!biz.phone.trim() || !biz.address.trim()) {
      showToast('Telefone e morada são obrigatórios.', 'error'); return
    }
    setSubmitting(s => ({ ...s, biz: true }))
    try {
      // Build the JSON business_data blob — only filled keys go in.
      // Phone + email are stashed here too rather than on User, so we
      // don't trigger the OTP-protected /change-email/ + /change-phone/
      // flows during onboarding. The seller's authoritative User
      // contact info is set at registration; this is "business
      // contact" data the platform uses for invoices, payouts, etc.
      const business_data = {
        account_type: biz.account_type,
        contact_phone: biz.phone.trim() || null,
        contact_email: biz.email.trim() || null,
        ...(isBiz ? {
          legal_company_name: biz.legal_company_name.trim(),
          business_licence_number: biz.business_licence_number.trim(),
          incorporation_date: biz.incorporation_date,
          business_address: biz.business_address.trim(),
          legal_rep_name: biz.legal_rep_name.trim(),
          legal_rep_id_number: biz.legal_rep_id_number.trim(),
          website: biz.website.trim(),
          annual_revenue: biz.annual_revenue,
        } : {}),
      }
      const fd = new FormData()
      if (biz.full_name) fd.append('full_name', biz.full_name.trim())
      if (biz.address)   fd.append('address',   biz.address.trim())
      if (biz.country)   fd.append('country',   biz.country.trim())
      fd.append('business_data', JSON.stringify(business_data))
      await client.patch('/api/v1/auth/profile/update/', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      showToast('Informações guardadas!')
      setOpenStep(2)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erro ao guardar.', 'error')
    } finally {
      setSubmitting(s => ({ ...s, biz: false }))
    }
  }

  const submitKyc = async () => {
    const f = kycForm
    if (!f.id_number || !f.id_expiry_date || !f.id_document || !f.selfie) {
      showToast('Preencha BI, data de validade, foto do BI e selfie.', 'error'); return
    }
    if (f.is_business_account && !f.business_licence) {
      showToast('Conta empresarial: carregue a licença comercial.', 'error'); return
    }
    setSubmitting(s => ({ ...s, kyc: true }))
    try {
      const fd = new FormData()
      fd.append('id_number', f.id_number.trim())
      fd.append('id_expiry_date', f.id_expiry_date)
      fd.append('id_document', f.id_document)
      fd.append('selfie', f.selfie)
      fd.append('is_business_account', f.is_business_account ? 'true' : 'false')
      if (f.id_document_back) fd.append('id_document_back', f.id_document_back)
      if (f.business_licence) fd.append('business_licence', f.business_licence)
      if (f.bank_proof)       fd.append('bank_proof', f.bank_proof)
      if (f.power_of_attorney) fd.append('power_of_attorney', f.power_of_attorney)
      const res = await client.post('/api/v1/verification/apply/', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setKyc(res.data)
      showToast('Documentos enviados! Aguarde aprovação.')
      setOpenStep(3)
    } catch (err) {
      const d = err.response?.data
      let msg = 'Erro ao enviar documentos.'
      if (d?.detail) msg = d.detail
      else if (d && typeof d === 'object') {
        const skip = new Set(['request_id', 'trace_id'])
        for (const [k, v] of Object.entries(d)) {
          if (skip.has(k)) continue
          const val = Array.isArray(v) ? v[0] : v
          if (typeof val === 'string') { msg = `${k}: ${val}`; break }
        }
      }
      showToast(msg, 'error')
    } finally {
      setSubmitting(s => ({ ...s, kyc: false }))
    }
  }

  const submitBank = async () => {
    const f = bankForm
    if (!f.bank_name.trim() || !f.account_name.trim() || !f.account_number.trim()) {
      showToast('Preencha banco, titular e número de conta.', 'error'); return
    }
    setSubmitting(s => ({ ...s, bank: true }))
    try {
      const res = await client.post('/api/v1/payments/bank-accounts/', {
        bank_name: f.bank_name.trim(),
        account_name: f.account_name.trim(),
        account_number: f.account_number.trim(),
        iban: f.iban.trim() || null,
        is_default: bankAccts.length === 0,
      })
      setBankAccts(prev => [...prev, res.data])
      showToast('Conta bancária adicionada!')
      setBankForm({ bank_name: '', account_name: '', account_number: '', iban: '' })
      setOpenStep(5)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erro ao adicionar conta.', 'error')
    } finally {
      setSubmitting(s => ({ ...s, bank: false }))
    }
  }

  // ── Derived state ───────────────────────────────────────────────
  const bizState = (biz.full_name && biz.phone) ? 'done' : 'todo'
  const kycState = (() => {
    if (!kyc) return 'todo'
    if (kyc.status === 'approved') return 'done'
    if (kyc.status === 'rejected') return 'rejected'
    return 'progress'
  })()
  const storeState = hasStore ? 'done' : 'todo'
  const bankState  = bankAccts.length > 0 ? 'done' : 'todo'

  const allReady = bizState === 'done' && kycState === 'done' && storeState === 'done' && bankState === 'done'
  const submitted = kyc && kyc.status !== 'pending'

  if (loading) {
    return (
      <SellerLayout title="Configuração">
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[1,2,3,4,5].map(i => (
            <div key={i} style={{ height: 72, borderRadius: 14, background: '#141414', animation: 'pulse 1.4s ease-in-out infinite' }} />
          ))}
          <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }`}</style>
        </div>
      </SellerLayout>
    )
  }

  return (
    <SellerLayout title="Configuração da Loja">
      {toast && (
        <div style={{
          position: 'fixed', top: 70, left: '50%', transform: 'translateX(-50%)', zIndex: 999,
          background: toast.type === 'error' ? '#dc2626' : '#10b981',
          color: '#FFFFFF', padding: '10px 18px', borderRadius: 14,
          ...S, fontSize: 13, fontWeight: 600, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>{toast.msg}</div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Hero */}
          <div style={{
            padding: '16px 18px',
            background: 'linear-gradient(135deg, rgba(201,168,76,0.18), rgba(201,168,76,0.04))',
            border: '1px solid rgba(201,168,76,0.3)', borderRadius: 16,
          }}>
            <p style={{ ...S, fontSize: 16, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>
              Bem-vindo, vendedor!
            </p>
            <p style={{ ...S, fontSize: 12, color: '#BFBFBF', lineHeight: 1.55 }}>
              Complete as 4 secções abaixo. A revisão dos documentos
              leva 1-3 dias úteis. Pode configurar a loja em paralelo.
            </p>
          </div>

          {/* §3 — Business Info (full spec) */}
          <StepCard
            number={1} title="Informação do vendedor"
            subtitle={biz.account_type === 'business' ? 'Empresa · 11 campos' : 'Individual · 7 campos'}
            state={bizState}
            open={openStep === 1}
            onToggle={() => setOpenStep(openStep === 1 ? null : 1)}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 6 }}>
              {/* §3 account-type toggle — drives which fields show */}
              <div>
                <label style={labelStyle}>Tipo de conta *</label>
                <div style={{ display: 'flex', gap: 6 }}>
                  {[
                    { v: 'individual', l: 'Individual' },
                    { v: 'business',   l: 'Empresa' },
                  ].map(o => (
                    <button key={o.v} type="button"
                      onClick={() => { setBiz(b => ({ ...b, account_type: o.v })); setKycForm(k => ({ ...k, is_business_account: o.v === 'business' })) }}
                      style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: `1.5px solid ${biz.account_type === o.v ? '#C9A84C' : '#2A2A2A'}`, background: biz.account_type === o.v ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: biz.account_type === o.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                      {o.l}
                    </button>
                  ))}
                </div>
              </div>

              {biz.account_type === 'business' ? (
                <>
                  <div>
                    <label style={labelStyle}>Nome legal da empresa *</label>
                    <input value={biz.legal_company_name} onChange={e => setBiz(b => ({ ...b, legal_company_name: e.target.value }))}
                      placeholder="MICHA Express, Lda" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>País de registo *</label>
                    <input value={biz.country} onChange={e => setBiz(b => ({ ...b, country: e.target.value }))} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Nº licença comercial *</label>
                    <input value={biz.business_licence_number} onChange={e => setBiz(b => ({ ...b, business_licence_number: e.target.value }))}
                      placeholder="NIF / Nº de registo" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Data de constituição *</label>
                    <input type="date" max={new Date(Date.now() - 86400000).toISOString().slice(0, 10)}
                      value={biz.incorporation_date} onChange={e => setBiz(b => ({ ...b, incorporation_date: e.target.value }))} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Endereço comercial *</label>
                    <textarea rows={2} value={biz.business_address} onChange={e => setBiz(b => ({ ...b, business_address: e.target.value }))}
                      placeholder="Rua, Bairro, Município, Província" style={{ ...inputStyle, resize: 'vertical' }} />
                  </div>
                  <div>
                    <label style={labelStyle}>Nome do representante legal *</label>
                    <input value={biz.legal_rep_name} onChange={e => setBiz(b => ({ ...b, legal_rep_name: e.target.value }))}
                      placeholder="Como aparece no BI" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Nº de BI do representante *</label>
                    <input value={biz.legal_rep_id_number} onChange={e => setBiz(b => ({ ...b, legal_rep_id_number: e.target.value }))} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Website / Redes sociais (opcional)</label>
                    <input type="url" value={biz.website} onChange={e => setBiz(b => ({ ...b, website: e.target.value }))}
                      placeholder="https://…" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Receita anual aproximada (opcional)</label>
                    <select value={biz.annual_revenue} onChange={e => setBiz(b => ({ ...b, annual_revenue: e.target.value }))} style={inputStyle}>
                      <option value="">— Seleccione —</option>
                      <option value="<10k">Menos de $10k</option>
                      <option value="10k-100k">$10k–$100k</option>
                      <option value="100k-1M">$100k–$1M</option>
                      <option value=">1M">Mais de $1M</option>
                    </select>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label style={labelStyle}>Nome legal completo *</label>
                    <input value={biz.full_name} onChange={e => setBiz(b => ({ ...b, full_name: e.target.value }))}
                      placeholder="Como aparece no BI" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>País de residência *</label>
                    <input value={biz.country} onChange={e => setBiz(b => ({ ...b, country: e.target.value }))} style={inputStyle} />
                  </div>
                </>
              )}

              <div>
                <label style={labelStyle}>Telefone *</label>
                <input value={biz.phone} onChange={e => setBiz(b => ({ ...b, phone: e.target.value }))}
                  placeholder="+244 9XX XXX XXX" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Email *</label>
                <input type="email" value={biz.email || user?.email || ''} onChange={e => setBiz(b => ({ ...b, email: e.target.value }))}
                  placeholder="contacto@empresa.ao" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Morada residencial *</label>
                <textarea rows={2} value={biz.address} onChange={e => setBiz(b => ({ ...b, address: e.target.value }))}
                  placeholder="Rua, Bairro, Município" style={{ ...inputStyle, resize: 'vertical' }} />
              </div>

              <button onClick={submitBiz} disabled={submitting.biz}
                style={{ padding: '12px 0', borderRadius: 10, border: 'none', background: submitting.biz ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                {submitting.biz ? 'A guardar…' : 'Guardar e continuar'}
              </button>
            </div>
          </StepCard>

          {/* §4 — KYC */}
          <StepCard
            number={2} title="Verificação de identidade (KYC)"
            subtitle="BI + selfie · revisão em 1-3 dias"
            state={kycState}
            open={openStep === 2}
            onToggle={() => setOpenStep(openStep === 2 ? null : 2)}
          >
            {kyc && kyc.status !== 'pending' ? (
              <div style={{ padding: '10px 0' }}>
                {kyc.status === 'approved' && (
                  <p style={{ ...S, fontSize: 13, color: '#10b981' }}>
                    ✓ Identidade verificada em {new Date(kyc.approved_at || kyc.reviewed_at).toLocaleDateString('pt-AO')}
                  </p>
                )}
                {kyc.status === 'under_review' && (
                  <p style={{ ...S, fontSize: 13, color: '#f59e0b' }}>
                    Documentos enviados. Revisão em curso.
                  </p>
                )}
                {kyc.status === 'rejected' && (
                  <>
                    <p style={{ ...S, fontSize: 13, color: '#ef4444', marginBottom: 6 }}>
                      Submissão rejeitada.
                    </p>
                    {kyc.rejection_reason && (
                      <p style={{ ...S, fontSize: 12, color: '#BFBFBF', marginBottom: 12 }}>
                        Motivo: {kyc.rejection_reason}
                      </p>
                    )}
                    <button onClick={() => setKyc(null)}
                      style={{ padding: '10px 16px', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 13, color: '#FFFFFF', cursor: 'pointer' }}>
                      Submeter novamente
                    </button>
                  </>
                )}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 6 }}>
                <div>
                  <label style={labelStyle}>Número do BI *</label>
                  <input value={kycForm.id_number} onChange={e => setKycForm(k => ({ ...k, id_number: e.target.value }))}
                    placeholder="000000000LA000" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Data de validade *</label>
                  <input type="date" value={kycForm.id_expiry_date}
                    onChange={e => setKycForm(k => ({ ...k, id_expiry_date: e.target.value }))}
                    style={inputStyle} />
                </div>
                <FilePicker label="Foto do BI (frente) *" accept="image/*"
                  file={kycForm.id_document}
                  hint="Os 4 cantos visíveis. JPG/PNG até 5MB."
                  onPick={f => setKycForm(k => ({ ...k, id_document: f }))} />
                <FilePicker label="Foto do BI (verso)" accept="image/*"
                  file={kycForm.id_document_back}
                  hint="Necessário para BI / cartão de cidadão. Não é necessário para passaporte."
                  onPick={f => setKycForm(k => ({ ...k, id_document_back: f }))} />
                <FilePicker label="Selfie segurando o BI *" accept="image/*"
                  file={kycForm.selfie}
                  hint="Rosto e BI visíveis na mesma foto."
                  onPick={f => setKycForm(k => ({ ...k, selfie: f }))} />

                {/* §4.2 — Business-account additional documents */}
                {kycForm.is_business_account && (
                  <>
                    <div style={{ padding: '10px 12px', background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.25)', borderRadius: 10 }}>
                      <p style={{ ...S, fontSize: 11, color: '#9CA3F4', lineHeight: 1.5 }}>
                        Conta empresarial — documentos adicionais necessários:
                      </p>
                    </div>
                    <FilePicker label="Licença comercial / Certificado *" accept="image/*,application/pdf"
                      file={kycForm.business_licence}
                      hint="JPG/PNG/PDF até 10MB. Válida (não expirada)."
                      onPick={f => setKycForm(k => ({ ...k, business_licence: f }))} />
                    <FilePicker label="Comprovativo bancário" accept="image/*,application/pdf"
                      file={kycForm.bank_proof}
                      hint="Extracto ou comprovativo da conta. Últimos 90 dias."
                      onPick={f => setKycForm(k => ({ ...k, bank_proof: f }))} />
                    <FilePicker label="Procuração (se aplicável)" accept="application/pdf"
                      file={kycForm.power_of_attorney}
                      hint="Só PDF — se quem submete não for o representante legal."
                      onPick={f => setKycForm(k => ({ ...k, power_of_attorney: f }))} />
                  </>
                )}
                <button onClick={submitKyc} disabled={submitting.kyc}
                  style={{ padding: '12px 0', borderRadius: 10, border: 'none', background: submitting.kyc ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                  {submitting.kyc ? 'A enviar…' : 'Enviar para revisão'}
                </button>
              </div>
            )}
          </StepCard>

          {/* §5 — Store Setup */}
          <StepCard
            number={3} title="Configurar a loja"
            subtitle={hasStore ? `Loja: ${storeName}` : 'Nome, banner, descrição, contactos'}
            state={storeState}
            open={openStep === 3}
            onToggle={() => setOpenStep(openStep === 3 ? null : 3)}
          >
            <div style={{ padding: '10px 0' }}>
              <p style={{ ...S, fontSize: 12, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 12 }}>
                {hasStore
                  ? 'A sua loja está criada. Pode editar nome, banner e políticas a qualquer momento.'
                  : 'Configure o nome, banner, descrição e políticas da loja num ecrã dedicado.'}
              </p>
              <button onClick={() => navigate('/seller/setup')}
                style={{ padding: '11px 18px', borderRadius: 10, border: 'none', background: hasStore ? '#1E1E1E' : '#C9A84C', color: hasStore ? '#FFFFFF' : '#0A0A0A', ...S, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
                {hasStore ? 'Editar loja' : 'Configurar loja →'}
              </button>
            </div>
          </StepCard>

          {/* §6 — Bank */}
          <StepCard
            number={4} title="Conta bancária para pagamentos"
            subtitle={bankAccts.length > 0 ? `${bankAccts.length} conta(s) adicionada(s)` : 'Como receber os pagamentos'}
            state={bankState}
            open={openStep === 4}
            onToggle={() => setOpenStep(openStep === 4 ? null : 4)}
          >
            {bankAccts.length > 0 && (
              <div style={{ marginBottom: 14, paddingTop: 6 }}>
                {bankAccts.map(a => (
                  <div key={a.id} style={{ padding: '10px 12px', background: '#0F0F0F', borderRadius: 10, marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ ...S, fontSize: 13, color: '#FFFFFF' }}>{a.bank_name} · {a.masked_number || `****${(a.account_number || '').slice(-4)}`}</span>
                    {a.is_default && <span style={{ ...S, fontSize: 10, color: '#C9A84C', fontWeight: 700 }}>PADRÃO</span>}
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 6 }}>
              <div>
                <label style={labelStyle}>Banco *</label>
                <input value={bankForm.bank_name} onChange={e => setBankForm(b => ({ ...b, bank_name: e.target.value }))}
                  placeholder="Ex: BAI, BFA, BIC, Standard Bank" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Titular da conta *</label>
                <input value={bankForm.account_name} onChange={e => setBankForm(b => ({ ...b, account_name: e.target.value }))}
                  placeholder="Como aparece nos documentos" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Número da conta *</label>
                <input value={bankForm.account_number} onChange={e => setBankForm(b => ({ ...b, account_number: e.target.value }))}
                  placeholder="Apenas dígitos" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>IBAN (opcional)</label>
                <input value={bankForm.iban} onChange={e => setBankForm(b => ({ ...b, iban: e.target.value }))}
                  placeholder="AO06 0000 0000 0000 0000 0000 0" style={inputStyle} />
              </div>
              <button onClick={submitBank} disabled={submitting.bank}
                style={{ padding: '12px 0', borderRadius: 10, border: 'none', background: submitting.bank ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                {submitting.bank ? 'A guardar…' : 'Adicionar conta'}
              </button>
            </div>
          </StepCard>

          {/* §7 — Submit / Status */}
          <StepCard
            number={5} title="Revisão e submissão"
            subtitle={allReady ? 'Pronto para submeter' : 'Complete as secções acima primeiro'}
            state={submitted ? (kycState === 'done' ? 'done' : kycState) : 'todo'}
            open={openStep === 5}
            onToggle={() => setOpenStep(openStep === 5 ? null : 5)}
          >
            <div style={{ paddingTop: 6 }}>
              {!allReady && (
                <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginBottom: 10 }}>
                  Falta(m): {[
                    bizState !== 'done' && 'Informação',
                    kycState === 'todo' && 'KYC',
                    storeState !== 'done' && 'Loja',
                    bankState !== 'done' && 'Banco',
                  ].filter(Boolean).join(', ')}
                </p>
              )}
              <button
                disabled={!allReady}
                onClick={() => navigate('/seller/application')}
                style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: 'none', background: allReady ? '#C9A84C' : '#2A2A2A', color: allReady ? '#0A0A0A' : '#555', ...S, fontSize: 14, fontWeight: 700, cursor: allReady ? 'pointer' : 'not-allowed' }}>
                {kycState === 'done' ? 'Ver estado da aplicação' : 'Ver estado da revisão →'}
              </button>
            </div>
          </StepCard>
        </div>
      </div>
    </SellerLayout>
  )
}
