import { useState, useEffect, useRef, useCallback } from 'react'
import { tokenStorage } from '@/api/tokenStorage'

const WS_BASE = import.meta.env.VITE_WS_URL
  || (window.location.protocol === 'https:' ? 'wss://' : 'ws://')
  + (import.meta.env.VITE_API_HOST || window.location.host)

export function useChatWS(conversationId) {
  const [messages, setMessages] = useState([])
  const [connected, setConnected] = useState(false)
  const [typingUsers, setTypingUsers] = useState(new Set())
  const [onlineUsers, setOnlineUsers] = useState(new Set())
  const ws = useRef(null)
  const reconnectTimer = useRef(null)
  const reconnectAttempts = useRef(0)
  const typingTimer = useRef(null)
  const isSending = useRef(false)

  const connect = useCallback(() => {
    if (!conversationId) return
    const token = tokenStorage.getAccessToken()
    const url = `${WS_BASE}/ws/chat/${conversationId}/?token=${token}`

    const socket = new WebSocket(url)
    ws.current = socket

    socket.onopen = () => {
      setConnected(true)
      reconnectAttempts.current = 0
    }

    socket.onmessage = (e) => {
      let data
      try { data = JSON.parse(e.data) } catch { return }

      if (data.type === 'chat_message') {
        const msg = {
          id: data.message_id || data.id || Date.now().toString(),
          content: data.message,
          sender: data.sender_id,
          senderName: data.sender_name,
          senderAvatar: data.sender_avatar,
          timestamp: data.timestamp ? new Date(data.timestamp) : new Date(),
          status: 'delivered',
          type: data.message_type || 'text',
          product: data.product || null,
        }
        setMessages(prev => {
          // deduplicate by id
          if (prev.find(m => m.id === msg.id)) return prev
          return [...prev, msg]
        })
        // clear typing for this sender
        setTypingUsers(prev => { const s = new Set(prev); s.delete(data.sender_id); return s })
      }

      if (data.type === 'typing') {
        if (data.is_typing) {
          setTypingUsers(prev => new Set([...prev, data.user_id]))
        } else {
          setTypingUsers(prev => { const s = new Set(prev); s.delete(data.user_id); return s })
        }
      }

      if (data.type === 'message_read') {
        setMessages(prev => prev.map(m =>
          m.id === data.message_id ? { ...m, status: 'seen' } : m
        ))
      }

      if (data.type === 'user.online') {
        setOnlineUsers(prev => new Set([...prev, data.user_id]))
      }

      if (data.type === 'user.offline') {
        setOnlineUsers(prev => { const s = new Set(prev); s.delete(data.user_id); return s })
      }
    }

    socket.onclose = (e) => {
      setConnected(false)
      // exponential backoff reconnect (max 30s)
      if (e.code !== 1000 && e.code !== 4001 && e.code !== 4003) {
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
        reconnectAttempts.current++
        reconnectTimer.current = setTimeout(connect, delay)
      }
    }

    socket.onerror = () => socket.close()
  }, [conversationId])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      ws.current?.close(1000)
    }
  }, [connect])

  const send = useCallback((content, type = 'text', extra = {}) => {
    if (!content?.trim() && type === 'text') return null
    const tempId = `temp-${Date.now()}`
    const optimistic = {
      id: tempId,
      content,
      sender: 'me',
      timestamp: new Date(),
      status: 'sending',
      type,
      ...extra,
    }
    setMessages(prev => [...prev, optimistic])

    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'chat_message', message: content, message_type: type, ...extra }))
      // optimistically mark as sent
      setTimeout(() => {
        setMessages(prev => prev.map(m => m.id === tempId ? { ...m, status: 'sent' } : m))
      }, 300)
    }
    return tempId
  }, [])

  const sendTyping = useCallback(() => {
    if (ws.current?.readyState !== WebSocket.OPEN) return
    ws.current.send(JSON.stringify({ type: 'typing', is_typing: true }))
    clearTimeout(typingTimer.current)
    typingTimer.current = setTimeout(() => {
      ws.current?.send(JSON.stringify({ type: 'typing', is_typing: false }))
    }, 2000)
  }, [])

  const markRead = useCallback((messageId) => {
    if (ws.current?.readyState !== WebSocket.OPEN) return
    ws.current.send(JSON.stringify({ type: 'message_read', message_id: messageId }))
  }, [])

  return { messages, setMessages, connected, typingUsers, onlineUsers, send, sendTyping, markRead }
}
