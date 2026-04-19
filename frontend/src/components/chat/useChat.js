import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * useChat — WebSocket chat hook
 * Falls back to mock mode when backend WebSocket isn't ready.
 * When Django Channels is ready, set VITE_WS_URL in .env
 */

const WS_URL = import.meta.env.VITE_WS_URL || null

export function useChat(conversationId) {
  const [messages, setMessages] = useState([])
  const [connected, setConnected] = useState(false)
  const [typing, setTyping] = useState(false)
  const wsRef = useRef(null)
  const typingTimer = useRef(null)

  useEffect(() => {
    if (!conversationId) return

    if (WS_URL) {
      // Real WebSocket connection
      const ws = new WebSocket(`${WS_URL}/ws/chat/${conversationId}/`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => setConnected(false)

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data)
        if (data.type === 'message') {
          setMessages(prev => [...prev, data.message])
        }
        if (data.type === 'typing') {
          setTyping(true)
          clearTimeout(typingTimer.current)
          typingTimer.current = setTimeout(() => setTyping(false), 2000)
        }
      }

      return () => ws.close()
    } else {
      // Mock mode — simulate connected
      setConnected(true)
    }
  }, [conversationId])

  const sendMessage = useCallback((content, type = 'text', extra = {}) => {
    const msg = {
      id: Date.now().toString(),
      content,
      type, // text | image | product | offer
      sender: 'me',
      timestamp: new Date(),
      status: 'sent',
      ...extra,
    }

    if (WS_URL && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', message: msg }))
    }

    // Always add locally for instant feedback
    setMessages(prev => [...prev, msg])

    // Simulate delivery confirmation
    setTimeout(() => {
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, status: 'delivered' } : m))
    }, 500)

    // Simulate seen
    setTimeout(() => {
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, status: 'seen' } : m))
    }, 2000)

    return msg
  }, [])

  const sendTyping = useCallback(() => {
    if (WS_URL && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'typing' }))
    }
  }, [])

  return { messages, setMessages, sendMessage, sendTyping, connected, typing }
}

// Mock conversations data
export const MOCK_CONVERSATIONS = [
  {
    id: 'conv-1',
    participant: { name: 'Moda Luanda', avatar: 'M', verified: true, role: 'seller' },
    lastMessage: 'Sim, temos em tamanho M e L. Posso enviar mais fotos?',
    lastTime: '14:32',
    unread: 2,
    product: { name: 'Vestido Capulana Premium', price: 8500, image_color: '#8B4513' },
    online: true,
  },
  {
    id: 'conv-2',
    participant: { name: 'TechShop Angola', avatar: 'T', verified: true, role: 'seller' },
    lastMessage: 'O produto tem garantia de 1 ano.',
    lastTime: '11:15',
    unread: 0,
    product: { name: 'Samsung A55', price: 185000, image_color: '#1a1a2e' },
    online: false,
  },
  {
    id: 'conv-3',
    participant: { name: 'Beauty Angola', avatar: 'B', verified: false, role: 'seller' },
    lastMessage: 'Obrigada pela sua compra! 😊',
    lastTime: 'Ontem',
    unread: 0,
    product: null,
    online: false,
  },
]

export const MOCK_MESSAGES = {
  'conv-1': [
    { id: '1', content: 'Olá! Tenho interesse no Vestido Capulana Premium. Tem em tamanho S?', sender: 'me', timestamp: new Date(Date.now() - 3600000), status: 'seen', type: 'text' },
    { id: '2', content: 'Bom dia! Obrigado pelo interesse. Infelizmente o tamanho S está esgotado neste momento.', sender: 'other', timestamp: new Date(Date.now() - 3500000), status: 'seen', type: 'text' },
    { id: '3', content: 'Ah, que pena. E em tamanho M ou L?', sender: 'me', timestamp: new Date(Date.now() - 3400000), status: 'seen', type: 'text' },
    { id: '4', content: 'Sim, temos em tamanho M e L. Posso enviar mais fotos?', sender: 'other', timestamp: new Date(Date.now() - 60000), status: 'seen', type: 'text' },
    { id: 'product-1', content: '', sender: 'other', timestamp: new Date(Date.now() - 55000), status: 'seen', type: 'product', product: { name: 'Vestido Capulana Premium', price: 8500, image_color: '#8B4513', id: '1' } },
  ],
  'conv-2': [
    { id: '5', content: 'Boa tarde, o Samsung A55 ainda está disponível?', sender: 'me', timestamp: new Date(Date.now() - 7200000), status: 'seen', type: 'text' },
    { id: '6', content: 'Sim, está disponível! Temos em preto e branco.', sender: 'other', timestamp: new Date(Date.now() - 7100000), status: 'seen', type: 'text' },
    { id: '7', content: 'O produto tem garantia de 1 ano.', sender: 'other', timestamp: new Date(Date.now() - 7000000), status: 'seen', type: 'text' },
  ],
  'conv-3': [
    { id: '8', content: 'Recebi o kit de skincare. Adorei! Muito obrigado.', sender: 'me', timestamp: new Date(Date.now() - 86400000), status: 'seen', type: 'text' },
    { id: '9', content: 'Obrigada pela sua compra! 😊', sender: 'other', timestamp: new Date(Date.now() - 86000000), status: 'seen', type: 'text' },
  ],
}

export function formatMessageTime(date) {
  const now = new Date()
  const diff = now - date
  if (diff < 60000) return 'Agora'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`
  if (diff < 86400000) return date.toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString('pt-AO', { day: '2-digit', month: 'short' })
}
