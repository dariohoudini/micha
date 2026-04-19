import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

const ANGOLA_PROVINCES = [
  'Luanda','Benguela','Huambo','Huíla','Cabinda','Uíge','Namibe',
  'Malanje','Bié','Moxico','Cunene','Cuando Cubango','Lunda Norte',
  'Lunda Sul','Kwanza Norte','Kwanza Sul','Bengo','Zaire',
]

const STEPS = [
  { id: 1, label: 'Dados do BI' },
  { id: 2, label: 'Fotos do BI' },
  { id: 3, label: 'Selfie' },
  { id: 4, label: 'Confirmação' },
]

// ── Photo Upload Box ──────────────────────────────────────────────────────────
function PhotoUploadBox({ label, sublabel, icon, file, onFile, accept = 'image/*' }) {
  const inputRef = useRef()
  const preview = file ? URL.createObjectURL(file) : null

  return (
    <button type="button" onClick={() => inputRef.current?.click()}
      style={{ width: '100%', borderRadius: 16, border: `2px dashed ${file ? '#C9A84C' : '#2A2A2A'}`, background: file ? 'rgba(201,168,76,0.05)' : '#141414', padding: '20px 16px', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, transition: 'all 0.2s' }}>
      <input ref={inputRef} type="file" accept={accept} style={{ display: 'none' }}
        onChange={e => e.target.files[0] && onFile(e.target.files[0])} />
      {preview ? (
        <div style={{ width: '100%', height: 160, borderRadius: 12, overflow: 'hidden', position: 'relative' }}>
          <img src={preview} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={{ position: 'absolute', top: 8, right: 8, background: '#C9A84C', borderRadius: '50%', width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
          </div>
        </div>
      ) : (
        <>
          <div style={{ width: 52, height: 52, borderRadius: 16, background: '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24 }}>
            {icon}
          </div>
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 4 }}>{label}</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{sublabel}</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.3)', borderRadius: 20, padding: '6px 14px' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C' }}>Carregar foto</span>
          </div>
        </>
      )}
    </button>
  )
}

// ── Oval Selfie Frame ─────────────────────────────────────────────────────────
function OvalSelfieCapture({ file, onFile }) {
  const inputRef = useRef()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20 }}>
      {/* Oval frame guide */}
      <div style={{ position: 'relative', width: 220, height: 280 }}>
        {/* Oval border */}
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid #C9A84C', background: file ? 'transparent' : 'rgba(201,168,76,0.05)' }} />

        {/* Preview or placeholder */}
        {file ? (
          <img src={URL.createObjectURL(file)} alt="Selfie"
            style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 10 }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', textAlign: 'center', padding: '0 20px' }}>
              Posicione o rosto dentro do oval
            </p>
          </div>
        )}

        {/* Corner guides */}
        {['top-left','top-right','bottom-left','bottom-right'].map(corner => (
          <div key={corner} style={{
            position: 'absolute',
            width: 20, height: 20,
            borderColor: '#C9A84C',
            borderStyle: 'solid',
            ...(corner === 'top-left' ? { top: 0, left: 0, borderWidth: '3px 0 0 3px', borderRadius: '8px 0 0 0' } : {}),
            ...(corner === 'top-right' ? { top: 0, right: 0, borderWidth: '3px 3px 0 0', borderRadius: '0 8px 0 0' } : {}),
            ...(corner === 'bottom-left' ? { bottom: 0, left: 0, borderWidth: '0 0 3px 3px', borderRadius: '0 0 0 8px' } : {}),
            ...(corner === 'bottom-right' ? { bottom: 0, right: 0, borderWidth: '0 3px 3px 0', borderRadius: '0 0 8px 0' } : {}),
          }} />
        ))}
      </div>

      {/* Instructions */}
      <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: '14px 16px', width: '100%' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#FFFFFF', marginBottom: 8 }}>Instruções para a selfie:</p>
        {[
          'Rosto bem iluminado e visível',
          'Olhe directamente para a câmara',
          'Sem óculos de sol ou chapéu',
          'Fundo simples e claro',
        ].map(tip => (
          <div key={tip} style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
            <span style={{ color: '#C9A84C', fontSize: 12 }}>•</span>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>{tip}</span>
          </div>
        ))}
      </div>

      <input ref={inputRef} type="file" accept="image/*" capture="user"
        style={{ display: 'none' }} onChange={e => e.target.files[0] && onFile(e.target.files[0])} />

      <button type="button" onClick={() => inputRef.current?.click()}
        className="btn-primary" style={{ width: '100%' }}>
        {file ? '📷 Tirar nova selfie' : '📷 Tirar selfie'}
      </button>

      {file && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
          </div>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#C9A84C' }}>Selfie capturada com sucesso</span>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function VerificationGatePage({ lockReason, rejectionReason, rejectionNotes, onComplete }) {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  const [formData, setFormData] = useState({
    full_name: '',
    bi_number: '',
    date_of_birth: '',
    place_of_birth: '',
    issuing_province: 'Luanda',
    bi_issue_date: '',
    bi_expiry_date: '',
  })
  const [files, setFiles] = useState({
    bi_front_photo: null,
    bi_back_photo: null,
    initial_selfie: null,
  })

  const updateForm = (field, value) =>
    setFormData(prev => ({ ...prev, [field]: value }))

  const canProceed = () => {
    if (step === 1) {
      return formData.full_name.trim() && formData.bi_number.trim() &&
             formData.date_of_birth && formData.bi_expiry_date
    }
    if (step === 2) return files.bi_front_photo && files.bi_back_photo
    if (step === 3) return !!files.initial_selfie
    return true
  }

  const handleSubmit = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = new FormData()
      Object.entries(formData).forEach(([k, v]) => v && data.append(k, v))
      Object.entries(files).forEach(([k, v]) => v && data.append(k, v))

      await client.post('/api/verification-gate/submit/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setSubmitted(true)
    } catch (err) {
      setError(err.response?.data?.error || 'Erro ao submeter. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  // ── Submitted state ─────────────────────────────────────────────────────────
  if (submitted) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A', padding: '32px 24px', textAlign: 'center' }}>
        <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', border: '2px solid rgba(201,168,76,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </div>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 12 }}>
          Verificação submetida
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.7, marginBottom: 32 }}>
          Os seus documentos estão a ser analisados pela equipa MICHA Express.
          Receberá uma notificação assim que a verificação for concluída.
          {'\n\n'}O processo demora normalmente menos de 24 horas.
        </p>
        <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16, width: '100%', marginBottom: 24 }}>
          {[
            { icon: '📄', text: 'BI analisado pelo administrador' },
            { icon: '🤳', text: 'Selfie comparada com foto do BI' },
            { icon: '✅', text: 'Aprovação em menos de 24h' },
          ].map(item => (
            <div key={item.text} style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
              <span style={{ fontSize: 18 }}>{item.icon}</span>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{item.text}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const inputStyle = {
    width: '100%', background: '#141414', border: '1px solid #2A2A2A',
    borderRadius: 12, padding: '13px 16px', fontFamily: "'DM Sans', sans-serif",
    fontSize: 14, color: '#FFFFFF', outline: 'none', boxSizing: 'border-box',
  }

  const labelStyle = {
    fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600,
    color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'block',
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>

      {/* Header */}
      <div style={{ padding: '0 20px 16px', flexShrink: 0 }}>
        {/* Lock reason banner */}
        {lockReason && (
          <div style={{ background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 12, padding: '10px 14px', marginBottom: 16 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#ef4444' }}>
              {lockReason === 'bi_expired' && '🔒 O seu BI expirou. Submeta um novo BI para reactivar a conta.'}
              {lockReason === 'selfie_overdue' && '🔒 A sua selfie mensal está em falta.'}
            </p>
          </div>
        )}

        {/* Rejection banner */}
        {rejectionReason && (
          <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: '12px 14px', marginBottom: 16 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#f59e0b', marginBottom: 4 }}>
              ⚠️ Verificação anterior rejeitada
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#f59e0b' }}>
              {rejectionNotes || 'Corrija o problema e submeta novamente.'}
            </p>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF' }}>
              Verificação de Identidade
            </h1>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>
              Obrigatório para vendedores MICHA Express
            </p>
          </div>
        </div>

        {/* Progress steps */}
        <div style={{ display: 'flex', gap: 4 }}>
          {STEPS.map(s => (
            <div key={s.id} style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ height: 3, borderRadius: 2, background: step >= s.id ? '#C9A84C' : '#1E1E1E', transition: 'background 0.3s' }} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, color: step >= s.id ? '#C9A84C' : '#9A9A9A', textAlign: 'center' }}>
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '8px 20px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Step 1 — BI Info */}
          {step === 1 && <>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>
              Dados do Bilhete de Identidade
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: -8 }}>
              Introduza os dados exactamente como aparecem no seu BI.
            </p>

            {[
              { field: 'full_name', label: 'Nome completo', placeholder: 'Ex: Maria João Silva', type: 'text' },
              { field: 'bi_number', label: 'Número do BI', placeholder: 'Ex: 004567823LA042', type: 'text' },
              { field: 'date_of_birth', label: 'Data de nascimento', placeholder: '', type: 'date' },
              { field: 'place_of_birth', label: 'Naturalidade', placeholder: 'Ex: Luanda', type: 'text' },
              { field: 'bi_issue_date', label: 'Data de emissão', placeholder: '', type: 'date' },
              { field: 'bi_expiry_date', label: 'Data de validade', placeholder: '', type: 'date' },
            ].map(field => (
              <div key={field.field}>
                <label style={labelStyle}>{field.label}</label>
                <input
                  type={field.type}
                  value={formData[field.field]}
                  onChange={e => updateForm(field.field, e.target.value)}
                  placeholder={field.placeholder}
                  style={inputStyle}
                />
              </div>
            ))}

            <div>
              <label style={labelStyle}>Província de emissão</label>
              <select value={formData.issuing_province}
                onChange={e => updateForm('issuing_province', e.target.value)}
                style={{ ...inputStyle }}>
                {ANGOLA_PROVINCES.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </>}

          {/* Step 2 — BI Photos */}
          {step === 2 && <>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>
              Fotos do Bilhete de Identidade
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: -8 }}>
              Fotografe o BI em local bem iluminado. Certifique-se que todos os dados são legíveis.
            </p>

            <PhotoUploadBox
              label="Frente do BI"
              sublabel="Foto com nome, número, foto e data de nascimento"
              icon="📄"
              file={files.bi_front_photo}
              onFile={f => setFiles(prev => ({ ...prev, bi_front_photo: f }))}
            />
            <PhotoUploadBox
              label="Verso do BI"
              sublabel="Foto com código de barras e informações adicionais"
              icon="📋"
              file={files.bi_back_photo}
              onFile={f => setFiles(prev => ({ ...prev, bi_back_photo: f }))}
            />

            <div style={{ background: 'rgba(201,168,76,0.05)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 12, padding: 14 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#C9A84C', marginBottom: 6 }}>
                📌 Dicas para boas fotos:
              </p>
              {['Sem reflexos ou sombras', 'BI plano e não dobrado', 'Todos os cantos visíveis', 'Foco nítido em todos os dados'].map(tip => (
                <p key={tip} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginBottom: 3 }}>• {tip}</p>
              ))}
            </div>
          </>}

          {/* Step 3 — Selfie */}
          {step === 3 && <>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>
              Selfie de verificação
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: -8 }}>
              Precisamos de uma selfie para confirmar que é a mesma pessoa do BI.
            </p>
            <OvalSelfieCapture
              file={files.initial_selfie}
              onFile={f => setFiles(prev => ({ ...prev, initial_selfie: f }))}
            />
          </>}

          {/* Step 4 — Review */}
          {step === 4 && <>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>
              Confirmar e submeter
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: -8 }}>
              Verifique os dados antes de submeter.
            </p>

            {/* Summary */}
            <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
              {[
                { label: 'Nome', value: formData.full_name },
                { label: 'Nº BI', value: formData.bi_number },
                { label: 'Data nasc.', value: formData.date_of_birth },
                { label: 'Validade', value: formData.bi_expiry_date },
                { label: 'Província', value: formData.issuing_province },
              ].map((item, i) => (
                <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderBottom: i < 4 ? '1px solid #1E1E1E' : 'none' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{item.label}</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF' }}>{item.value || '—'}</span>
                </div>
              ))}
            </div>

            {/* Photos summary */}
            <div style={{ display: 'flex', gap: 10 }}>
              {[
                { label: 'Frente BI', file: files.bi_front_photo },
                { label: 'Verso BI', file: files.bi_back_photo },
                { label: 'Selfie', file: files.initial_selfie, round: true },
              ].map(item => (
                <div key={item.label} style={{ flex: 1, textAlign: 'center' }}>
                  <div style={{ height: 70, borderRadius: item.round ? '50%' : 10, overflow: 'hidden', background: '#1E1E1E', border: `2px solid ${item.file ? '#C9A84C' : '#2A2A2A'}`, marginBottom: 4 }}>
                    {item.file && <img src={URL.createObjectURL(item.file)} alt={item.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                  </div>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: item.file ? '#C9A84C' : '#9A9A9A' }}>
                    {item.file ? '✓ ' : ''}{item.label}
                  </span>
                </div>
              ))}
            </div>

            {/* Legal notice */}
            <div style={{ background: 'rgba(201,168,76,0.05)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 12, padding: 14 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.6 }}>
                Ao submeter, confirma que os dados e documentos são autênticos e pertencentes a si.
                A MICHA Express irá rever os documentos em conformidade com a Lei 22/11 de Angola.
                Documentos falsos resultarão em suspensão permanente e reporte às autoridades competentes.
              </p>
            </div>

            {error && (
              <div style={{ background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 10, padding: 12 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#ef4444' }}>{error}</p>
              </div>
            )}
          </>}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: '14px 20px', paddingBottom: 'max(28px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E', flexShrink: 0, display: 'flex', gap: 10 }}>
        {step > 1 && (
          <button onClick={() => setStep(s => s - 1)} className="btn-secondary"
            style={{ width: 'auto', padding: '1rem 20px' }}>
            Anterior
          </button>
        )}
        {step < 4 ? (
          <button onClick={() => setStep(s => s + 1)} className="btn-primary"
            disabled={!canProceed()} style={{ flex: 1, opacity: canProceed() ? 1 : 0.4 }}>
            Continuar
          </button>
        ) : (
          <button onClick={handleSubmit} className="btn-primary"
            disabled={loading} style={{ flex: 1, opacity: loading ? 0.6 : 1 }}>
            {loading ? 'A submeter...' : '🔐 Submeter verificação'}
          </button>
        )}
      </div>
    </div>
  )
}
