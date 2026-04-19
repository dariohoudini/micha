import { z } from 'zod'

// ── Reusable field schemas ─────────────────────────────────────────────────
const phone = z.string()
  .min(9, 'Número inválido')
  .max(9, 'Número inválido')
  .regex(/^\d+$/, 'Apenas números')

const email = z.string()
  .email('Email inválido')
  .transform(v => v.toLowerCase().trim())

const password = z.string()
  .min(8, 'Mínimo 8 caracteres')
  .regex(/[A-Z]/, 'Deve conter pelo menos uma maiúscula')
  .regex(/[0-9]/, 'Deve conter pelo menos um número')

const username = z.string()
  .min(3, 'Mínimo 3 caracteres')
  .max(30, 'Máximo 30 caracteres')
  .regex(/^[a-z0-9_]+$/, 'Apenas letras minúsculas, números e _')
  .transform(v => v.toLowerCase().trim())

// ── Form schemas ───────────────────────────────────────────────────────────
export const loginSchema = z.object({
  email,
  password: z.string().min(1, 'Insira a palavra-passe'),
})

export const registerSchema = z.object({
  email,
  username,
  full_name: z.string().optional(),
  phone: phone.optional().or(z.literal('')),
  password,
  password2: z.string(),
  account_type: z.enum(['buyer', 'seller']),
  privacy_consent: z.literal(true, { errorMap: () => ({ message: 'Deve aceitar a Política de Privacidade' }) }),
  terms_consent: z.literal(true, { errorMap: () => ({ message: 'Deve aceitar os Termos de Uso' }) }),
}).refine(data => data.password === data.password2, {
  message: 'As palavras-passe não coincidem',
  path: ['password2'],
})

export const forgotPasswordSchema = z.object({ email })

export const resetPasswordSchema = z.object({
  otp: z.string().length(6, 'Código deve ter 6 dígitos'),
  new_password: password,
  confirm_password: z.string(),
}).refine(data => data.new_password === data.confirm_password, {
  message: 'As palavras-passe não coincidem',
  path: ['confirm_password'],
})

export const checkoutSchema = z.object({
  full_name: z.string().min(2, 'Insira o nome completo'),
  phone: phone,
  province: z.string().min(1, 'Selecione a província'),
  address: z.string().min(5, 'Insira o endereço completo'),
  reference: z.string().optional(),
  payment_method: z.enum(['multicaixa', 'cash']),
})

export const sellerSetupSchema = z.object({
  store_name: z.string().min(2, 'Insira o nome da loja').max(50, 'Máximo 50 caracteres'),
  category: z.string().min(1, 'Selecione uma categoria'),
  description: z.string().max(500, 'Máximo 500 caracteres').optional(),
  nif: z.string().optional(),
  province: z.string().min(1),
  phone: phone,
  whatsapp: z.string().optional(),
  instagram: z.string().optional(),
  returns_policy: z.string().optional(),
})

export const productSchema = z.object({
  name: z.string().min(3, 'Mínimo 3 caracteres').max(100, 'Máximo 100 caracteres'),
  category: z.string().min(1, 'Selecione uma categoria'),
  condition: z.enum(['new', 'used', 'refurbished']),
  price: z.number({ invalid_type_error: 'Insira um preço válido' }).positive('Preço deve ser positivo'),
  original_price: z.number().positive().optional().nullable(),
  stock: z.number({ invalid_type_error: 'Insira o stock' }).int().positive('Stock deve ser positivo'),
  description: z.string().min(10, 'Mínimo 10 caracteres').max(2000, 'Máximo 2000 caracteres'),
  weight: z.number().positive().optional().nullable(),
  express: z.boolean(),
})
