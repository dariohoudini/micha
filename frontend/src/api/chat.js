import api from './client'

export const chatApi = {
  listConversations: () =>
    api.get('/api/v1/chat/conversations/'),

  createConversation: (data) =>
    api.post('/api/v1/chat/conversations/', data),

  getMessages: (conversationId, params = {}) =>
    api.get(`/api/v1/chat/conversations/${conversationId}/messages/`, { params }),

  sendMessage: (conversationId, data) =>
    api.post(`/api/v1/chat/conversations/${conversationId}/messages/`, data),

  markRead: (conversationId) =>
    api.patch(`/api/v1/chat/conversations/${conversationId}/read/`),

  archive: (conversationId) =>
    api.patch(`/api/v1/chat/conversations/${conversationId}/archive/`),

  report: (conversationId, data) =>
    api.post(`/api/v1/chat/conversations/${conversationId}/report/`, data),

  getQuickReplies: () =>
    api.get('/api/v1/chat/quick-replies/'),

  saveQuickReply: (data) =>
    api.post('/api/v1/chat/quick-replies/', data),
}
