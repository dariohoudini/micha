import { useState, useEffect } from 'react'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const GOLD = '#C9A84C', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A', GREEN = '#059669'

export default function ReferralPage() {
  const [referral, setReferral] = useState(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/api/v1/auth/referral/').then(r => setReferral(r.data)).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const copy = () => {
    navigator.clipboard.writeText(referral?.code || '').then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  }

  const share = () => {
    const text = encodeURIComponent(`Usa o meu código ${referral?.code} na MICHA Express e ganha 100 Micha Stars na primeira compra! 🛍️`)
    window.open(`https://wa.me/?text=${text}`, '_blank')
  }

  return (
    <BuyerLayout title="Referências">
      <div style={{ flex: 1, overflowY: 'auto', background: BG, padding: '16px 16px 80px' }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: TEXT, margin: '0 0 4px' }}>Convida amigos</h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: MUTED, margin: '0 0 24px' }}>Ganha 200 Micha Stars por cada amigo que se registar</p>

        {/* Referral code */}
        <div style={{ background: CARD, borderRadius: 16, border: `1px solid ${BORDER}`, padding: 20, marginBottom: 16 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>O teu código</p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, color: GOLD, margin: 0, letterSpacing: 4 }}>
              {loading ? '------' : referral?.code || 'MICHA00'}
            </p>
            <button onClick={copy} style={{ padding: '8px 14px', borderRadius: 10, border: `1px solid ${BORDER}`, background: copied ? GREEN : 'none', color: copied ? TEXT : MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12, cursor: 'pointer', transition: 'all 0.2s' }}>
              {copied ? '✓ Copiado' : 'Copiar'}
            </button>
          </div>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
          {[
            { label: 'Amigos convidados', value: referral?.total_referrals || 0 },
            { label: 'Stars ganhas', value: (referral?.total_referrals || 0) * 200 },
          ].map((s, i) => (
            <div key={i} style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, padding: 14, textAlign: 'center' }}>
              <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: GOLD, margin: '0 0 4px' }}>{s.value}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>{s.label}</p>
            </div>
          ))}
        </div>

        {/* How it works */}
        <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 16, marginBottom: 16 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: TEXT, margin: '0 0 12px' }}>Como funciona</p>
          {[
            { icon: '📤', text: 'Partilha o teu código com amigos' },
            { icon: '📱', text: 'O amigo regista-se com o teu código' },
            { icon: '⭐', text: 'Ambos ganham 100 Micha Stars' },
            { icon: '🛍️', text: 'Usas as stars para descontos' },
          ].map((step, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: i < 3 ? 10 : 0 }}>
              <span style={{ fontSize: 20 }}>{step.icon}</span>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: 0 }}>{step.text}</p>
            </div>
          ))}
        </div>

        {/* Share button */}
        <button onClick={share} style={{ width: '100%', padding: 14, borderRadius: 14, border: 'none', background: '#25D366', color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
          Partilhar no WhatsApp
        </button>
      </div>
    </BuyerLayout>
  )
}
