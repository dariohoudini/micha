/**
 * AI Description Generator component for SellerProductNewPage
 * Add this to your existing SellerProductNewPage.jsx in Step 2
 *
 * Usage: Drop <AIDescriptionGenerator> into the description field area
 */
import { useState } from 'react'
import { generateProductDescription, improveDescription } from '@/api/ai'

export function AIDescriptionGenerator({ productName, category, price, language = 'pt', onGenerated }) {
  const [loading, setLoading] = useState(false)
  const [generated, setGenerated] = useState(null)
  const [error, setError] = useState(null)

  const handleGenerate = async () => {
    if (!productName) {
      setError('Insira o nome do produto primeiro.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await generateProductDescription({
        name: productName,
        category: category || '',
        price: price || 0,
        language,
      })
      setGenerated(res.data)
      onGenerated?.(res.data)
    } catch (err) {
      setError('Geração falhou. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Generate button */}
      <button type="button" onClick={handleGenerate} disabled={loading || !productName}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          padding: '10px 0', borderRadius: 12,
          border: '1px solid rgba(201,168,76,0.3)',
          background: loading ? 'rgba(201,168,76,0.05)' : 'rgba(201,168,76,0.1)',
          cursor: loading || !productName ? 'not-allowed' : 'pointer',
          opacity: !productName ? 0.4 : 1,
          transition: 'all 0.2s',
        }}>
        {loading ? (
          <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
          </div>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          </svg>
        )}
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#C9A84C' }}>
          {loading ? 'A gerar com IA...' : '✨ Gerar descrição com IA'}
        </span>
      </button>

      {error && (
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#dc2626' }}>{error}</p>
      )}

      {/* Generated result */}
      {generated && (
        <div style={{ background: 'rgba(201,168,76,0.05)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
            </svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#C9A84C', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Gerado pela IA
            </span>
          </div>

          {generated.title && (
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Título sugerido</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>{generated.title}</p>
            </div>
          )}

          {generated.highlights?.length > 0 && (
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Pontos-chave</p>
              {generated.highlights.map((h, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
                  <span style={{ color: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 12 }}>•</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF' }}>{h}</span>
                </div>
              ))}
            </div>
          )}

          {generated.tags?.length > 0 && (
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Tags sugeridas</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {generated.tags.map(tag => (
                  <span key={tag} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', padding: '3px 8px', borderRadius: 20 }}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', lineHeight: 1.6, padding: '10px 14px', background: '#141414', borderRadius: 10 }}>
            {generated.description}
          </p>

          <button type="button" onClick={() => onGenerated?.(generated)}
            style={{ padding: '10px 0', borderRadius: 10, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#0A0A0A', cursor: 'pointer' }}>
            Usar esta descrição
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * AI Trust Score Badge component
 * Add to seller cards and product detail page
 */
export function TrustScoreBadge({ sellerId, compact = false }) {
  const [score, setScore] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const loadScore = async () => {
    if (loaded) return
    try {
      const { getSellerTrustScore } = await import('@/api/ai')
      const res = await getSellerTrustScore(sellerId)
      setScore(res.data)
    } catch {}
    setLoaded(true)
  }

  // Lazy load on first render
  if (!loaded) { loadScore() }

  if (!score?.public || !score?.badge) return null

  const { badge, overall_score } = score

  if (compact) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: `${badge.color}18`, border: `1px solid ${badge.color}40`, borderRadius: 20, padding: '2px 8px' }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill={badge.color}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: badge.color }}>
          {overall_score?.toFixed(0)}
        </span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: `${badge.color}10`, border: `1px solid ${badge.color}30`, borderRadius: 12, padding: '8px 12px' }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill={badge.color}>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
      <div>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: badge.color }}>{badge.label}</p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>Pontuação: {overall_score?.toFixed(1)}/100</p>
      </div>
    </div>
  )
}

/**
 * AI Chat Button — opens AI assistant from product detail page
 */
export function AIChatButton({ productId, productName, language = 'pt' }) {
  const [open, setOpen] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [starting, setStarting] = useState(false)

  const handleOpen = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (!conversationId) {
      setStarting(true)
      try {
        const { startAIChat } = await import('@/api/ai')
        const res = await startAIChat({ productId, productName, language })
        setConversationId(res.data.conversation_id)
        setMessages([{ role: 'assistant', content: res.data.greeting }])
      } catch {
        setMessages([{ role: 'assistant', content: language === 'pt'
          ? 'Olá! Como posso ajudá-lo com este produto?'
          : 'Hello! How can I help you with this product?' }])
      } finally {
        setStarting(false)
      }
    }
  }

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setLoading(true)

    try {
      const { sendAIChatMessage } = await import('@/api/ai')
      const res = await sendAIChatMessage(conversationId, userMsg)
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.message }])
    } catch {
      const fallback = language === 'pt' ? 'Desculpe, ocorreu um erro. Tente novamente.' : 'Sorry, an error occurred. Please try again.'
      setMessages(prev => [...prev, { role: 'assistant', content: fallback }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ position: 'fixed', bottom: 90, right: 16, zIndex: 50 }}>
      {/* Chat window */}
      {open && (
        <div style={{ position: 'absolute', bottom: 60, right: 0, width: 300, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 16, overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
          {/* Header */}
          <div style={{ padding: '12px 14px', background: '#1E1E1E', borderBottom: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg, #C9A84C, #A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF' }}>MICHA Assistente</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#059669' }}>Online</p>
            </div>
            <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Messages */}
          <div style={{ height: 240, overflowY: 'auto', padding: '12px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {starting ? (
              <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
                <div style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
              </div>
            ) : messages.map((msg, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{ maxWidth: '80%', padding: '8px 12px', borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px', background: msg.role === 'user' ? '#C9A84C' : '#1E1E1E', border: msg.role !== 'user' ? '1px solid #2A2A2A' : 'none' }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: msg.role === 'user' ? '#0A0A0A' : '#FFFFFF', lineHeight: 1.5 }}>{msg.content}</p>
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', gap: 4, padding: '8px 12px' }}>
                {[0,1,2].map(i => <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#9A9A9A', animation: `bounce 1.2s ${i * 0.2}s infinite` }} />)}
                <style>{`@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}`}</style>
              </div>
            )}
          </div>

          {/* Input */}
          <div style={{ padding: '10px 12px', borderTop: '1px solid #2A2A2A', display: 'flex', gap: 8 }}>
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder={language === 'pt' ? 'Faça uma pergunta...' : 'Ask a question...'}
              style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 10, padding: '8px 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF', outline: 'none' }} />
            <button onClick={handleSend} disabled={!input.trim() || loading}
              style={{ width: 34, height: 34, borderRadius: 10, background: input.trim() && !loading ? '#C9A84C' : '#2A2A2A', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background 0.2s' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={input.trim() && !loading ? '#0A0A0A' : '#9A9A9A'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* FAB button */}
      <button onClick={handleOpen}
        style={{ width: 50, height: 50, borderRadius: '50%', background: open ? '#1E1E1E' : 'linear-gradient(135deg, #C9A84C, #A67C35)', border: open ? '1px solid #2A2A2A' : 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 16px rgba(0,0,0,0.3)', transition: 'all 0.3s' }}>
        {open
          ? <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
        }
      </button>
    </div>
  )
}
