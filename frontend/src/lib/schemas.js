import { z } from 'zod'

// ── Shared ─────────────────────────────────────────────────────────────────
const phoneAO = z
  .string()
  .min(9, 'Número inválido')
  .max(9, 'Número inválido')
  .regex(/^[9][0-9]{8}$/, 'Número deve começar com 9 e ter 9 dígitos')

const password = z
  .string()
  .min(8, 'Mínimo 8 caracteres')
  .regex(/[A-Z]/, 'Deve conter pelo menos uma letra maiúscula')
  .regex(/[0-9]/, 'Deve conter pelo menos um número')

// ── Auth schemas ───────────────────────────────────────────────────────────
export const loginSchema = z.object({
  email: z.string().email('Email inválido').toLowerCase(),
  password: z.string().min(1, 'Insira a palavra-passe'),
})

export const registerSchema = z.object({
  email: z.string().email('Email inválido').toLowerCase(),
  username: z
    .string()
    .min(3, 'Mínimo 3 caracteres')
    .max(30, 'Máximo 30 caracteres')
    .regex(/^[a-zA-Z0-9_]+$/, 'Apenas letras, números e _')
    .toLowerCase(),
  full_name: z.string().optional(),
  phone: phoneAO.optional().or(z.literal('')),
  password,
  password2: z.string(),
  privacy_consent: z.literal(true, { errorMap: () => ({ message: 'Obrigatório aceitar' }) }),
  terms_consent: z.literal(true, { errorMap: () => ({ message: 'Obrigatório aceitar' }) }),
  account_type: z.enum(['buyer', 'seller']),
}).refine(data => data.password === data.password2, {
  message: 'As palavras-passe não coincidem',
  path: ['password2'],
})

export const forgotPasswordSchema = z.object({
  email: z.string().email('Email inválido').toLowerCase(),
})

export const resetPasswordSchema = z.object({
  otp: z.string().length(6, 'Código deve ter 6 dígitos'),
  new_password: password,
  confirm_password: z.string(),
}).refine(data => data.new_password === data.confirm_password, {
  message: 'As palavras-passe não coincidem',
  path: ['confirm_password'],
})

export const changePasswordSchema = z.object({
  old_password: z.string().min(1, 'Insira a palavra-passe actual'),
  new_password: password,
  confirm_password: z.string(),
}).refine(data => data.new_password === data.confirm_password, {
  message: 'As palavras-passe não coincidem',
  path: ['confirm_password'],
})

// ── Checkout schemas ───────────────────────────────────────────────────────
export const checkoutSchema = z.object({
  full_name: z.string().min(2, 'Nome inválido'),
  phone: phoneAO,
  province: z.string().min(1, 'Selecione uma província'),
  address: z.string().min(5, 'Endereço muito curto'),
  reference: z.string().optional(),
  payment_method: z.enum(['multicaixa', 'cash']),
})

// ── Product schemas ────────────────────────────────────────────────────────
export const productSchema = z.object({
  name: z.string().min(3, 'Nome muito curto').max(100, 'Nome muito longo'),
  category: z.string().min(1, 'Selecione uma categoria'),
  condition: z.enum(['new', 'used', 'refurbished']),
  price: z.coerce.number().positive('Preço deve ser positivo'),
  original_price: z.coerce.number().positive().optional().or(z.literal('')),
  stock: z.coerce.number().int().positive('Stock deve ser positivo'),
  description: z.string().min(10, 'Descrição muito curta').max(2000, 'Descrição muito longa'),
  weight: z.coerce.number().positive().optional().or(z.literal('')),
  express: z.boolean(),
})

// ── Store setup schemas ────────────────────────────────────────────────────
export const storeSchema = z.object({
  store_name: z.string().min(2, 'Nome muito curto').max(60, 'Nome muito longo'),
  category: z.string().min(1, 'Selecione uma categoria'),
  description: z.string().max(500, 'Máximo 500 caracteres').optional(),
  nif: z.string().optional(),
  province: z.string().min(1, 'Selecione uma província'),
  phone: phoneAO,
  whatsapp: z.string().optional(),
  instagram: z.string().optional(),
  returns_policy: z.string().optional(),
})

// ── Profile edit schema ────────────────────────────────────────────────────
export const profileSchema = z.object({
  full_name: z.string().optional(),
  username: z
    .string()
    .min(3, 'Mínimo 3 caracteres')
    .regex(/^[a-zA-Z0-9_]+$/, 'Apenas letras, números e _')
    .toLowerCase(),
  phone: phoneAO.optional().or(z.literal('')),
  city: z.string().optional(),
  bio: z.string().max(200, 'Máximo 200 caracteres').optional(),
})
