import api from '@/api/client'
/**
 * MICHA Express — Helper Bot
 * Contextual onboarding guide for buyers + proactive seller coach
 * Rule-based, fast, always available
 */
import { useState, useEffect, useRef } from 'react'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const GREEN = '#059669'

// ─── Local storage helpers ────────────────────────────────────────
const storage = {
  get: (key) => { try { return JSON.parse(localStorage.getItem(`micha_${key}`)) } catch { return null } },
  set: (key, val) => { try { localStorage.setItem(`micha_${key}`, JSON.stringify(val)) } catch {} },
}

// ─── BUYER GUIDE SCRIPTS ─────────────────────────────────────────
// Each screen has steps. Each step highlights an element + shows tip.
export const BUYER_GUIDES = {
  home: [
    { id: 'search', title: 'Pesquisa rápida', message: 'Toca aqui para pesquisar qualquer produto. Podes pesquisar por nome, marca ou categoria.', icon: '🔍', anchor: 'search-bar' },
    { id: 'categories', title: 'Navega por categoria', message: 'Desliza estas categorias para filtrar produtos. Toca numa para ver só o que queres.', icon: '📦', anchor: 'category-pills' },
    { id: 'express', title: 'Entrega Express', message: 'Produtos com o símbolo ⚡ são entregues em Luanda no mesmo dia. Procura o selo dourado.', icon: '⚡', anchor: 'feed' },
    { id: 'wishlist', title: 'Guarda para depois', message: 'Toca no coração num produto para o guardar na tua lista de desejos. Serás notificado se o preço baixar.', icon: '❤️', anchor: 'feed' },
  ],
  product: [
    { id: 'gallery', title: 'Ver mais fotos', message: 'Desliza as fotos para a esquerda para ver mais ângulos do produto.', icon: '📷', anchor: 'product-gallery' },
    { id: 'seller', title: 'Verifica o vendedor', message: 'Toca no nome do vendedor para ver a sua loja, avaliações e tempo de resposta médio.', icon: '🏪', anchor: 'seller-info' },
    { id: 'qa', title: 'Faz perguntas', message: 'Tens dúvidas? Usa a secção de Perguntas & Respostas. O vendedor responde e todos os compradores vêem a resposta.', icon: '💬', anchor: 'qa-section' },
    { id: 'cart', title: 'Adicionar ao carrinho', message: 'Toca em "Adicionar ao carrinho" para comprar. Podes adicionar vários produtos antes de pagar.', icon: '🛒', anchor: 'add-to-cart' },
  ],
  cart: [
    { id: 'quantity', title: 'Ajusta a quantidade', message: 'Toca em + ou - para ajustar quantas unidades queres de cada produto.', icon: '🔢', anchor: 'cart-items' },
    { id: 'promo', title: 'Tens um código?', message: 'Se tens um código promocional, introduz-o antes de pagar para receber o teu desconto.', icon: '🎁', anchor: 'promo-input' },
    { id: 'checkout', title: 'Pagamento seguro', message: 'Paga com Multicaixa Express. Recebes uma referência para pagar na tua app bancária ou ATM.', icon: '🔒', anchor: 'checkout-btn' },
  ],
  orders: [
    { id: 'track', title: 'Segue o teu pedido', message: 'Toca num pedido para ver o estado em tempo real — desde a confirmação até à entrega.', icon: '📍', anchor: 'orders-list' },
    { id: 'chat', title: 'Fala com o vendedor', message: 'Tens algum problema? Podes enviar uma mensagem directa ao vendedor a partir do teu pedido.', icon: '💬', anchor: 'orders-list' },
    { id: 'dispute', title: 'Problema com a entrega?', message: 'Se algo correu mal, toca em "Reportar problema" no teu pedido. A MICHA garante a tua protecção.', icon: '🛡️', anchor: 'orders-list' },
  ],
}

// ─── SELLER GUIDE SCRIPTS ────────────────────────────────────────
export const SELLER_GUIDES = {
  dashboard: [
    { id: 'stats', title: 'O teu resumo diário', message: 'Aqui vês as tuas vendas, pedidos e visitas de hoje. Verifica todos os dias para acompanhar o crescimento.', icon: '📊', anchor: 'stats-cards' },
    { id: 'pending', title: 'Confirma os pedidos', message: 'Pedidos novos precisam de confirmação em menos de 2 horas. Compradores cancelam se demorares muito.', icon: '⚠️', anchor: 'pending-orders' },
    { id: 'analytics', title: 'Entende os teus números', message: 'O gráfico mostra a tua receita por dia. Identificas os dias mais fortes para planear promoções.', icon: '📈', anchor: 'revenue-chart' },
  ],
  products: [
    { id: 'add', title: 'Adiciona produtos', message: 'Toca em "Novo produto" para listar um artigo. Boas fotos e descrições detalhadas vendem 3x mais.', icon: '➕', anchor: 'add-product-btn' },
    { id: 'photos', title: 'Fotos fazem a diferença', message: 'Produtos com 4+ fotos têm 60% mais vendas. Usa luz natural e mostra todos os ângulos.', icon: '📸', anchor: 'products-list' },
    { id: 'stock', title: 'Mantém o stock actualizado', message: 'Produtos com stock 0 ficam invisíveis na pesquisa. Actualiza o stock assim que recebes mercadoria.', icon: '📦', anchor: 'products-list' },
    { id: 'price', title: 'Preços competitivos', message: 'A MICHA mostra ao comprador outros vendedores do mesmo produto. Mantém um preço competitivo.', icon: '💰', anchor: 'products-list' },
  ],
  orders: [
    { id: 'confirm', title: 'Confirma rapidamente', message: 'Confirma pedidos em menos de 1 hora. Vendedores rápidos têm melhor posição na pesquisa.', icon: '✅', anchor: 'kanban-board' },
    { id: 'tracking', title: 'Adiciona rastreamento', message: 'Quando enviares, adiciona o número de rastreamento. O comprador é notificado automaticamente.', icon: '🚚', anchor: 'kanban-board' },
    { id: 'notes', title: 'Lê as notas do comprador', message: 'Os pedidos com notas especiais têm uma etiqueta dourada. Lê sempre antes de preparar.', icon: '📝', anchor: 'order-notes' },
  ],
}

// ─── SELLER COACH RULES ──────────────────────────────────────────
// Rule-based suggestions based on product/order data
export async function getAISellerTips() {
  try {
    const res = await api.post('/api/v1/ai/flash-sale-target/')
    const suggestions = res.data.suggestions || []
    return suggestions.map(s => ({
      id: `ai_flash_${s.product_id}`,
      type: 'ai_suggestion',
      priority: 'high',
      icon: '🤖',
      title: 'Sugestão da IA MICHA',
      message: s.reason || `A IA sugere criar uma Flash Sale para "${s.product_title}" para aumentar as vendas.`,
      actions: [{ label: 'Criar Flash Sale', action: 'flash_sale', productId: s.product_id }],
    }))
  } catch { return [] }
}

export function getSellerCoachTips(products = [], orders = [], stats = {}) {
  const tips = []

  // Stale products (no sales in 14+ days)
  const stale = products.filter(p => {
    if (!p.last_sold_at && p.created_at) {
      const days = (Date.now() - new Date(p.created_at)) / 86400000
      return days > 14 && p.quantity > 0
    }
    if (p.last_sold_at) {
      const days = (Date.now() - new Date(p.last_sold_at)) / 86400000
      return days > 14
    }
    return false
  }).slice(0, 3)

  stale.forEach(p => {
    tips.push({
      id: `stale_${p.id}`,
      type: 'stale',
      priority: 'high',
      icon: '⏰',
      title: 'Produto parado há muito tempo',
      message: `"${p.title}" não tem vendas há mais de 14 dias. Tenta baixar o preço em 10–15% ou criar uma Flash Sale para atrair compradores.`,
      actions: [
        { label: 'Criar Flash Sale', action: 'flash_sale', productId: p.id },
        { label: 'Editar preço', action: 'edit_price', productId: p.id },
      ],
      product: p,
    })
  })

  // Low stock warning
  const lowStock = products.filter(p => p.quantity > 0 && p.quantity <= (p.low_stock_threshold || 5))
  if (lowStock.length > 0) {
    tips.push({
      id: 'low_stock',
      type: 'stock',
      priority: 'high',
      icon: '📦',
      title: `${lowStock.length} produto${lowStock.length > 1 ? 's' : ''} com stock baixo`,
      message: `${lowStock.map(p => `"${p.title}"`).join(', ')} ${lowStock.length > 1 ? 'têm' : 'tem'} poucas unidades. Repõe o stock para não perderes vendas.`,
      actions: [{ label: 'Ver produtos', action: 'view_products' }],
    })
  }

  // No photos products
  const noPhotos = products.filter(p => !p.images || p.images.length === 0).slice(0, 2)
  if (noPhotos.length > 0) {
    tips.push({
      id: 'no_photos',
      type: 'quality',
      priority: 'medium',
      icon: '📸',
      title: 'Produtos sem fotos vendem menos',
      message: `${noPhotos.map(p => `"${p.title}"`).join(', ')} ${noPhotos.length > 1 ? 'não têm' : 'não tem'} fotos. Adiciona pelo menos 3 fotos para aumentar as vendas.`,
      actions: [{ label: 'Adicionar fotos', action: 'edit_product', productId: noPhotos[0]?.id }],
    })
  }

  // Pending orders too long
  const longPending = orders.filter(o => {
    if (o.status !== 'pending') return false
    const hours = (Date.now() - new Date(o.created_at)) / 3600000
    return hours > 1
  })
  if (longPending.length > 0) {
    tips.push({
      id: 'pending_orders',
      type: 'urgent',
      priority: 'urgent',
      icon: '🚨',
      title: `${longPending.length} pedido${longPending.length > 1 ? 's' : ''} à espera há mais de 1 hora`,
      message: 'Compradores podem cancelar se não confirmares. Confirma agora para manter a tua reputação.',
      actions: [{ label: 'Ver pedidos', action: 'view_orders' }],
    })
  }

  // No description products
  const noDesc = products.filter(p => !p.description || p.description.length < 50).slice(0, 2)
  if (noDesc.length > 0) {
    tips.push({
      id: 'no_desc',
      type: 'quality',
      priority: 'medium',
      icon: '✍️',
      title: 'Descrições curtas reduzem as vendas',
      message: `${noDesc.map(p => `"${p.title}"`).join(', ')} ${noDesc.length > 1 ? 'têm' : 'tem'} descrições muito curtas. Detalha materiais, tamanhos e condição do produto.`,
      actions: [{ label: 'Melhorar descrição', action: 'edit_product', productId: noDesc[0]?.id }],
    })
  }

  // Good performance tip
  if (stats.today_revenue > 0 && stats.conversion_rate > 3) {
    tips.push({
      id: 'good_performance',
      type: 'success',
      priority: 'low',
      icon: '🌟',
      title: 'Estás a ir muito bem!',
      message: `A tua taxa de conversão é de ${stats.conversion_rate?.toFixed(1)}% — acima da média da plataforma. Continua assim!`,
      actions: [{ label: 'Ver analytics', action: 'view_analytics' }],
    })
  }

  // Sort by priority
  const order = { urgent: 0, high: 1, medium: 2, low: 3 }
  return tips.sort((a, b) => order[a.priority] - order[b.priority])
}

// ─── GUIDE TOOLTIP COMPONENT ─────────────────────────────────────
function GuideTooltip({ step, total, tip, onNext, onSkip }) {
  return (
    <div style={{
      position: 'fixed', bottom: 90, left: 16, right: 16, zIndex: 10000,
      background: CARD, borderRadius: 18, border: `1.5px solid ${GOLD}`,
      boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      animation: 'slideUp 0.3s ease',
    }}>
      <style>{`@keyframes slideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}`}</style>

      {/* Header */}
      <div style={{ padding: '14px 16px 0', display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(201,168,76,0.15)', border: `1px solid rgba(201,168,76,0.3)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>
          {tip.icon}
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: TEXT, margin: 0 }}>{tip.title}</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: '2px 0 0' }}>Passo {step + 1} de {total}</p>
        </div>
        <button onClick={onSkip} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED, padding: 4 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      {/* Progress dots */}
      <div style={{ display: 'flex', gap: 4, padding: '10px 16px 0', justifyContent: 'center' }}>
        {Array.from({ length: total }).map((_, i) => (
          <div key={i} style={{ width: i === step ? 20 : 6, height: 6, borderRadius: 3, background: i === step ? GOLD : BORDER, transition: 'all 0.3s' }} />
        ))}
      </div>

      {/* Message */}
      <div style={{ padding: '10px 16px 14px' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: 0, lineHeight: 1.6 }}>{tip.message}</p>
      </div>

      {/* Actions */}
      <div style={{ padding: '0 16px 16px', display: 'flex', gap: 8 }}>
        <button onClick={onSkip} style={{ flex: 1, padding: '10px', borderRadius: 10, border: `1px solid ${BORDER}`, background: 'none', color: MUTED, fontFamily: "'DM Sans', sans-serif", fontSize: 12, cursor: 'pointer' }}>
          Saltar guia
        </button>
        <button onClick={onNext} style={{ flex: 2, padding: '10px', borderRadius: 10, border: 'none', background: GOLD, color: '#000', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
          {step < total - 1 ? 'Próximo →' : 'Percebido! ✓'}
        </button>
      </div>
    </div>
  )
}

// ─── BUYER GUIDE HOOK ────────────────────────────────────────────
export function useBuyerGuide(screen) {
  const steps = BUYER_GUIDES[screen] || []
  const storageKey = `guide_done_${screen}`
  const [active, setActive] = useState(false)
  const [step, setStep] = useState(0)

  useEffect(() => {
    const done = storage.get(storageKey)
    if (!done && steps.length > 0) {
      const timer = setTimeout(() => setActive(true), 800)
      return () => clearTimeout(timer)
    }
  }, [screen])

  const next = () => {
    if (step < steps.length - 1) setStep(s => s + 1)
    else { setActive(false); storage.set(storageKey, true) }
  }

  const skip = () => { setActive(false); storage.set(storageKey, true) }
  const restart = () => { setStep(0); setActive(true) }

  return {
    active,
    currentTip: steps[step],
    step,
    total: steps.length,
    next,
    skip,
    restart,
  }
}

// ─── BUYER GUIDE RENDERER ────────────────────────────────────────
export function BuyerGuide({ screen }) {
  const guide = useBuyerGuide(screen)
  if (!guide.active || !guide.currentTip) return null
  return <GuideTooltip step={guide.step} total={guide.total} tip={guide.currentTip} onNext={guide.next} onSkip={guide.skip} />
}

// ─── SELLER COACH TIP CARD ───────────────────────────────────────
function CoachTipCard({ tip, onAction, onDismiss }) {
  const priorityColors = {
    urgent: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', dot: '#EF4444' },
    high: { bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.3)', dot: '#F59E0B' },
    medium: { bg: 'rgba(59,130,246,0.08)', border: 'rgba(59,130,246,0.3)', dot: '#3B82F6' },
    low: { bg: 'rgba(5,150,105,0.08)', border: 'rgba(5,150,105,0.3)', dot: GREEN },
    success: { bg: 'rgba(5,150,105,0.08)', border: 'rgba(5,150,105,0.3)', dot: GREEN },
  }
  const c = priorityColors[tip.priority] || priorityColors.medium

  return (
    <div style={{ background: c.bg, border: `1.5px solid ${c.border}`, borderRadius: 14, padding: 14, animation: 'fadeIn 0.3s ease' }}>
      <style>{`@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: c.dot, flexShrink: 0, marginTop: 5 }} />
        <div style={{ flex: 1 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: TEXT, margin: '0 0 4px' }}>
            {tip.icon} {tip.title}
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: 0, lineHeight: 1.6 }}>{tip.message}</p>
        </div>
        <button onClick={() => onDismiss(tip.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED, padding: 2, flexShrink: 0 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      {tip.actions?.length > 0 && (
        <div style={{ display: 'flex', gap: 8, paddingLeft: 18 }}>
          {tip.actions.map((action, i) => (
            <button key={i} onClick={() => onAction(action, tip)} style={{
              padding: '7px 12px', borderRadius: 8, border: `1px solid ${c.border}`,
              background: i === 0 ? c.dot : 'none',
              color: i === 0 ? (tip.priority === 'low' || tip.priority === 'success' ? TEXT : '#000') : c.dot,
              fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, cursor: 'pointer'
            }}>{action.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── SELLER COACH PANEL ──────────────────────────────────────────
export function SellerCoachPanel({ products = [], orders = [], stats = {}, onAction }) {
  const tips = getSellerCoachTips(products, orders, stats)
  const [dismissed, setDismissed] = useState(() => storage.get('dismissed_tips') || [])
  const [expanded, setExpanded] = useState(true)

  const visible = tips.filter(t => !dismissed.includes(t.id))

  const dismiss = (id) => {
    const next = [...dismissed, id]
    setDismissed(next)
    storage.set('dismissed_tips', next)
  }

  if (visible.length === 0) return null

  return (
    <div style={{ margin: '0 0 16px' }}>
      {/* Header */}
      <button onClick={() => setExpanded(!expanded)} style={{
        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 0', background: 'none', border: 'none', cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(201,168,76,0.15)', border: `1px solid rgba(201,168,76,0.25)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>
            💡
          </div>
          <div style={{ textAlign: 'left' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: TEXT, margin: 0 }}>Sugestões do MICHA</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: 0 }}>{visible.length} dica{visible.length > 1 ? 's' : ''} para melhorar as tuas vendas</p>
          </div>
        </div>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="2" strokeLinecap="round"
          style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="18 15 12 9 6 15"/>
        </svg>
      </button>

      {/* Tips */}
      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {visible.map(tip => (
            <CoachTipCard key={tip.id} tip={tip} onAction={onAction} onDismiss={dismiss} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── HELP BUTTON (floating) ──────────────────────────────────────
export function HelpButton({ screen, isSeller = false, onOpen }) {
  const [pulse, setPulse] = useState(true)
  useEffect(() => { const t = setTimeout(() => setPulse(false), 5000); return () => clearTimeout(t) }, [])

  return (
    <button onClick={onOpen} style={{
      position: 'fixed', bottom: 90, right: 16, zIndex: 999,
      width: 48, height: 48, borderRadius: '50%', border: 'none', cursor: 'pointer',
      background: isSeller ? '#3B82F6' : GOLD,
      boxShadow: `0 4px 16px ${isSeller ? 'rgba(59,130,246,0.4)' : 'rgba(201,168,76,0.4)'}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      animation: pulse ? 'helpPulse 1s ease 2' : 'none',
    }}>
      <style>{`@keyframes helpPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}`}</style>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={isSeller ? '#fff' : '#000'} strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </button>
  )
}

// ─── HELP SHEET ──────────────────────────────────────────────────
function HelpSheet({ screen, isSeller, onClose, onStartGuide }) {
  const guide = isSeller ? SELLER_GUIDES[screen] : BUYER_GUIDES[screen]
  const faqs = isSeller ? SELLER_FAQS : BUYER_FAQS
  const [openFaq, setOpenFaq] = useState(null)

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 10001, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      {/* Backdrop */}
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.7)' }} />

      {/* Sheet */}
      <div style={{ position: 'relative', background: '#111', borderRadius: '20px 20px 0 0', maxHeight: '80vh', overflowY: 'auto', animation: 'sheetUp 0.3s ease' }}>
        <style>{`@keyframes sheetUp{from{transform:translateY(100%)}to{transform:translateY(0)}}`}</style>

        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 0' }}>
          <div style={{ width: 40, height: 4, borderRadius: 2, background: BORDER }} />
        </div>

        {/* Header */}
        <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: `1px solid ${BORDER}` }}>
          <div style={{ width: 40, height: 40, borderRadius: 12, background: 'rgba(201,168,76,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
            {isSeller ? '🏪' : '🛍️'}
          </div>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: TEXT, margin: 0 }}>Centro de Ajuda MICHA</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: 0 }}>{isSeller ? 'Guia do Vendedor' : 'Guia do Comprador'}</p>
          </div>
        </div>

        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Start guide button */}
          {guide && (
            <button onClick={() => { onStartGuide(); onClose() }} style={{
              padding: '14px', borderRadius: 14, border: 'none', cursor: 'pointer',
              background: isSeller ? '#3B82F6' : GOLD,
              color: isSeller ? TEXT : '#000',
              fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Iniciar guia desta página ({guide.length} passos)
            </button>
          )}

          {/* FAQs */}
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '0 0 10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Perguntas frequentes
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {faqs.map((faq, i) => (
                <div key={i} style={{ background: CARD, borderRadius: 12, overflow: 'hidden', border: `1px solid ${BORDER}` }}>
                  <button onClick={() => setOpenFaq(openFaq === i ? null : i)} style={{
                    width: '100%', padding: '13px 14px', background: 'none', border: 'none', cursor: 'pointer',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                  }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: TEXT, textAlign: 'left', fontWeight: 500 }}>{faq.q}</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="2" strokeLinecap="round"
                      style={{ transform: openFaq === i ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }}>
                      <polyline points="18 15 12 9 6 15"/>
                    </svg>
                  </button>
                  {openFaq === i && (
                    <div style={{ padding: '0 14px 13px' }}>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED, margin: 0, lineHeight: 1.6 }}>{faq.a}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Contact */}
          <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 14 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: TEXT, margin: '0 0 4px' }}>Ainda tens dúvidas?</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '0 0 12px' }}>A nossa equipa está disponível de Segunda a Sábado, das 8h às 20h.</p>
            <button onClick={() => window.open('https://wa.me/244923000000', '_blank')} style={{
              width: '100%', padding: '11px', borderRadius: 10, border: 'none', cursor: 'pointer',
              background: '#25D366', color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
              Falar com suporte no WhatsApp
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── FAQ DATA ────────────────────────────────────────────────────
const BUYER_FAQS = [
  { q: 'Como faço o pagamento?', a: 'Aceitamos Multicaixa Express. Recebes uma referência de pagamento que podes usar na tua app bancária, ATM ou caixas Multicaixa.' },
  { q: 'Quanto tempo demora a entrega?', a: 'Em Luanda, entregamos em 2-6 horas para produtos Express. Para outras províncias, demora 2-5 dias úteis.' },
  { q: 'E se o produto não chegar?', a: 'O teu pagamento fica em escrow até confirmares a entrega. Se não receberes, abre uma disputa e devolvemos o dinheiro.' },
  { q: 'Posso devolver um produto?', a: 'Sim! Tens 7 dias após a entrega para devolver um produto que não corresponda à descrição ou que chegue danificado.' },
  { q: 'Como contacto o vendedor?', a: 'Podes enviar mensagem directamente ao vendedor na página do produto ou no teu pedido.' },
]

const SELLER_FAQS = [
  { q: 'Quando recebo o pagamento?', a: 'O pagamento é liberado 3 dias após a confirmação de entrega pelo comprador. Podes ver o calendário de pagamentos na tua carteira.' },
  { q: 'Qual é a comissão da MICHA?', a: 'A MICHA cobra entre 5% e 10% de comissão dependendo da categoria. Podes ver a taxa exacta na página do teu produto.' },
  { q: 'Como aumento as minhas vendas?', a: 'Produtos com boas fotos (4+), descrições detalhadas e preços competitivos vendem 3x mais. Usa Flash Sales para produtos parados.' },
  { q: 'O que acontece se não confirmar um pedido?', a: 'Se não confirmares em 2 horas, o comprador pode cancelar automaticamente. Muitos cancelamentos afectam a tua posição na pesquisa.' },
  { q: 'Como funciona a resolução de disputas?', a: 'A MICHA faz de mediador. Tens 48h para responder a uma disputa com provas. Mantém sempre registos das tuas entregas.' },
]

// ─── MAIN HELPER BOT COMPONENT ───────────────────────────────────
export default function HelperBot({ screen = 'home', isSeller = false, products = [], orders = [], stats = {} }) {
  const [sheetOpen, setSheetOpen] = useState(false)
  const [guideActive, setGuideActive] = useState(false)
  const guides = isSeller ? SELLER_GUIDES : BUYER_GUIDES
  const steps = guides[screen] || []
  const [step, setStep] = useState(0)
  const storageKey = `guide_done_${isSeller ? 'seller' : 'buyer'}_${screen}`

  // Auto-start guide for first timers
  useEffect(() => {
    const done = storage.get(storageKey)
    if (!done && steps.length > 0) {
      const timer = setTimeout(() => setGuideActive(true), 1200)
      return () => clearTimeout(timer)
    }
  }, [screen])

  const nextStep = () => {
    if (step < steps.length - 1) setStep(s => s + 1)
    else { setGuideActive(false); storage.set(storageKey, true); setStep(0) }
  }

  const skipGuide = () => { setGuideActive(false); storage.set(storageKey, true); setStep(0) }
  const startGuide = () => { setStep(0); setGuideActive(true) }

  return (
    <>
      {/* Seller coach tips */}
      {isSeller && screen === 'dashboard' && (
        <SellerCoachPanel
          products={products}
          orders={orders}
          stats={stats}
          onAction={(action) => {
            if (action.action === 'view_orders') window.location.href = '/seller/orders'
            if (action.action === 'view_products') window.location.href = '/seller/products'
            if (action.action === 'view_analytics') window.location.href = '/seller/analytics'
            if (action.action === 'edit_product' && action.productId) window.location.href = `/seller/product/${action.productId}`
          }}
        />
      )}

      {/* Floating help button */}
      {!guideActive && !sheetOpen && (
        <HelpButton screen={screen} isSeller={isSeller} onOpen={() => setSheetOpen(true)} />
      )}

      {/* Guide tooltip */}
      {guideActive && steps[step] && (
        <GuideTooltip
          step={step}
          total={steps.length}
          tip={steps[step]}
          onNext={nextStep}
          onSkip={skipGuide}
        />
      )}

      {/* Help sheet */}
      {sheetOpen && (
        <HelpSheet
          screen={screen}
          isSeller={isSeller}
          onClose={() => setSheetOpen(false)}
          onStartGuide={startGuide}
        />
      )}
    </>
  )
}
