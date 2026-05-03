import { toast } from '@/components/ui/Toast'

const DEFAULT_MESSAGES = {
  400: 'Pedido inválido. Verifique os dados inseridos.',
  401: 'Sessão expirada. Por favor, inicie sessão novamente.',
  403: 'Não tem permissão para realizar esta acção.',
  404: 'O recurso solicitado não foi encontrado.',
  409: 'Conflito — o registo já existe.',
  422: 'Os dados fornecidos são inválidos.',
  429: 'Demasiadas tentativas. Tente novamente em breve.',
  500: 'Erro interno do servidor. Tente novamente.',
  502: 'Serviço temporariamente indisponível.',
  503: 'Serviço em manutenção. Tente mais tarde.',
}

export function parseApiError(error) {
  if (!error) return 'Ocorreu um erro inesperado.'

  const status = error?.response?.status
  const data = error?.response?.data

  if (data) {
    if (typeof data === 'string') return data
    if (data.detail) return data.detail
    if (data.message) return data.message
    if (data.non_field_errors?.length) return data.non_field_errors[0]

    const fieldErrors = Object.entries(data)
      .filter(([, v]) => Array.isArray(v) && v.length > 0)
      .map(([k, v]) => `${k}: ${v[0]}`)

    if (fieldErrors.length) return fieldErrors[0]
  }

  if (status && DEFAULT_MESSAGES[status]) return DEFAULT_MESSAGES[status]

  if (!navigator.onLine) return 'Sem ligação à internet.'

  return error?.message || 'Ocorreu um erro inesperado.'
}

export function useApiError() {
  const handleError = (error, fallback) => {
    const message = parseApiError(error) || fallback || 'Ocorreu um erro.'
    toast.error(message)
    return message
  }

  return { handleError, parseApiError }
}

export function getFieldErrors(error) {
  const data = error?.response?.data
  if (!data || typeof data !== 'object') return {}
  const out = {}
  for (const [key, val] of Object.entries(data)) {
    if (Array.isArray(val)) out[key] = val[0]
    else if (typeof val === 'string') out[key] = val
  }
  return out
}
