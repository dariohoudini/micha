/**
 * src/pages/verification/MonthlySelfieGatePage.jsx
 *
 * Monthly selfie renewal gate.
 * Shown when seller's monthly selfie is overdue.
 * Total lockout — only this screen is visible.
 */
import { useState, useRef } from 'react'
import client from '@/api/client'

export default function MonthlySelfieGatePage({ onComplete }) {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef()

  const handleSubmit = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const data = new FormData()
      data.append('selfie', file)
      await client.post('/api/verification-gate/monthly-selfie/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setSubmitted(true)
    } catch (err) {
      setError(err.response?.data?.error || 'Erro ao submeter. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  if (submitted) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A', padding: '32px 24px', textAlign: 'center' }}>
        <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', border: '2px solid rgba(201,168,76,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>
          Selfie submetida!
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.7, marginBottom: 32 }}>
          A sua selfie está a ser analisada pelo administrador MICHA Express.
          A sua conta será reactivada assim que for aprovada.
          Isto demora normalmente menos de 24 horas.
        </p>
        <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16, width: '100%' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {file && (
              <img src={URL.createObjectURL(file)} alt="Selfie"
                style={{ width: 60, height: 60, borderRadius: '50%', objectFit: 'cover', border: '2px solid #C9A84C', flexShrink: 0 }} />
            )}
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 2 }}>Selfie submetida com sucesso</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>Aprovação em até 24 horas</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>

      {/* Header */}
      <div style={{ padding: '0 20px 20px', flexShrink: 0 }}>
        <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: '12px 14px', marginBottom: 20 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#f59e0b', marginBottom: 2 }}>
            🔒 Conta temporariamente bloqueada
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#f59e0b' }}>
            A sua selfie mensal está em falta. Submeta uma selfie para reactivar.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>
              Selfie Mensal
            </h1>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>
              Renovação mensal de identidade
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 20px 20px', display: 'flex', flexDirection: 'column', gap: 20, alignItems: 'center' }}>

          {/* Oval frame */}
          <div style={{ position: 'relative', width: 220, height: 280 }}>
            <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: `3px solid ${file ? '#C9A84C' : '#2A2A2A'}`, background: file ? 'transparent' : 'rgba(201,168,76,0.03)', transition: 'border-color 0.3s' }} />
            {file ? (
              <img src={URL.createObjectURL(file)} alt="Selfie"
                style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }} />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 10 }}>
                <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                </svg>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', textAlign: 'center', padding: '0 20px' }}>
                  Posicione o rosto dentro do oval
                </p>
              </div>
            )}
          </div>

          {/* Why monthly */}
          <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: '14px 16px', width: '100%' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 8 }}>
              Porque fazemos isto mensalmente?
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.6 }}>
              A verificação mensal garante que a mesma pessoa continua a operar a conta, 
              protegendo compradores e vendedores de fraude de identidade — 
              um problema crescente no comércio electrónico em Angola.
            </p>
          </div>

          {/* Instructions */}
          <div style={{ background: 'rgba(201,168,76,0.05)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 12, padding: 14, width: '100%' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#C9A84C', marginBottom: 8 }}>
              📋 Instruções:
            </p>
            {[
              'Rosto bem iluminado e visível',
              'Olhe directamente para a câmara',
              'Sem óculos de sol, chapéu ou máscara',
              'Fundo simples — de preferência parede clara',
            ].map(tip => (
              <p key={tip} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 4 }}>
                • {tip}
              </p>
            ))}
          </div>

          {error && (
            <div style={{ background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 10, padding: 12, width: '100%' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#ef4444' }}>{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: '14px 20px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <input ref={inputRef} type="file" accept="image/*" capture="user"
          style={{ display: 'none' }}
          onChange={e => e.target.files[0] && setFile(e.target.files[0])} />

        <button onClick={() => inputRef.current?.click()} className="btn-secondary">
          📷 {file ? 'Tirar nova selfie' : 'Tirar selfie'}
        </button>

        {file && (
          <button onClick={handleSubmit} className="btn-primary"
            disabled={loading} style={{ opacity: loading ? 0.6 : 1 }}>
            {loading ? 'A submeter...' : '✓ Submeter selfie'}
          </button>
        )}
      </div>
    </div>
  )
}
