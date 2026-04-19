/**
 * src/pages/seller/rentals/VerificationPage.jsx
 * ID + selfie verification before listing
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

export default function VerificationPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [idFile, setIdFile] = useState(null)
  const [selfieFile, setSelfieFile] = useState(null)
  const [docType, setDocType] = useState('bi')
  const [docNumber, setDocNumber] = useState('')
  const [isMicheiro, setIsMicheiro] = useState(false)
  const [commissionDesc, setCommissionDesc] = useState('')

  const handleSubmit = async () => {
    if (!idFile || !selfieFile || !docNumber) return
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('id_document_type', docType)
      formData.append('id_document_number', docNumber)
      formData.append('id_document_image', idFile)
      formData.append('selfie_image', selfieFile)
      formData.append('is_micheiro', isMicheiro)
      if (isMicheiro) formData.append('micheiro_description', commissionDesc)

      await client.post('/api/rentals/verify/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      navigate('/rentals/create')
    } catch (err) {
      console.error('Verification failed:', err.response?.data)
    } finally {
      setLoading(false)
    }
  }

  const FileUpload = ({ label, file, onChange, accept = 'image/*' }) => (
    <div>
      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>{label}</p>
      <label style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 14, borderRadius: 14, border: `1.5px dashed ${file ? '#059669' : '#2A2A2A'}`, background: file ? 'rgba(5,150,105,0.06)' : '#141414', cursor: 'pointer' }}>
        <input type="file" accept={accept} onChange={e => onChange(e.target.files[0])} style={{ display: 'none' }} />
        {file
          ? <><span style={{ fontSize: 24 }}>✓</span><div><p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#059669', marginBottom: 1 }}>{file.name}</p><p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>Toque para trocar</p></div></>
          : <><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg><p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Toque para carregar</p></>
        }
      </label>
    </div>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A', paddingTop: 'max(52px, env(safe-area-inset-top))' }}>
      <div style={{ padding: '0 20px', flexShrink: 0 }}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', marginBottom: 20 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        </button>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>Verificação de identidade</h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6, marginBottom: 24 }}>
          Para garantir a segurança da plataforma, precisamos verificar a sua identidade antes de publicar anúncios.
        </p>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '0 20px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Doc type */}
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>Tipo de documento</p>
            <div style={{ display: 'flex', gap: 8 }}>
              {[{ v: 'bi', l: 'BI' }, { v: 'passport', l: 'Passaporte' }, { v: 'residence', l: 'Residência' }].map(d => (
                <button key={d.v} onClick={() => setDocType(d.v)}
                  style={{ flex: 1, padding: '10px 0', borderRadius: 12, border: `1.5px solid ${docType === d.v ? '#C9A84C' : '#2A2A2A'}`, background: docType === d.v ? 'rgba(201,168,76,0.1)' : '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: docType === d.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                  {d.l}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 8 }}>Número do documento *</p>
            <input type="text" placeholder="ex: 005123456LA045" value={docNumber} onChange={e => setDocNumber(e.target.value)}
              style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 14, outline: 'none', boxSizing: 'border-box' }} />
          </div>

          <FileUpload label="Foto do documento (frente) *" file={idFile} onChange={setIdFile} />
          <FileUpload label="Selfie com documento *" file={selfieFile} onChange={setSelfieFile} />

          <label style={{ display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', padding: '12px 14px', background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E' }}>
            <input type="checkbox" checked={isMicheiro} onChange={() => setIsMicheiro(v => !v)} style={{ width: 18, height: 18 }} />
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF', marginBottom: 1 }}>Sou Micheiro</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>Trabalho como intermediário imobiliário</p>
            </div>
          </label>

          {isMicheiro && (
            <input type="text" placeholder="Descreva o seu serviço de intermediação..." value={commissionDesc} onChange={e => setCommissionDesc(e.target.value)}
              style={{ width: '100%', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 12, padding: '12px 14px', color: '#FFFFFF', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
          )}

          <div style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)', borderRadius: 12, padding: '12px 14px' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#818cf8', lineHeight: 1.6 }}>
              🔒 Os seus documentos são usados exclusivamente para verificação de identidade e não são partilhados com terceiros.
            </p>
          </div>
        </div>
      </div>

      <div style={{ padding: '14px 20px', paddingBottom: 'max(24px, env(safe-area-inset-bottom))', borderTop: '1px solid #1E1E1E' }}>
        <button onClick={handleSubmit} disabled={!idFile || !selfieFile || !docNumber || loading}
          style={{ width: '100%', padding: '14px 0', borderRadius: 14, border: 'none', background: idFile && selfieFile && docNumber && !loading ? '#C9A84C' : '#2A2A2A', fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: idFile && selfieFile && docNumber && !loading ? '#0A0A0A' : '#9A9A9A', cursor: idFile && selfieFile && docNumber && !loading ? 'pointer' : 'not-allowed' }}>
          {loading ? 'A submeter...' : 'Submeter verificação'}
        </button>
      </div>
    </div>
  )
}
