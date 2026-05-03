import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuthStore as useAuth } from '@/stores/authStore'
import { useChangePassword } from '@/hooks/useQueries'
import PageHeader from '@/components/ui/PageHeader'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'

const changePasswordSchema = z.object({
  old_password: z.string().min(1, 'Insira a senha atual'),
  new_password: z.string().min(8, 'Mínimo 8 caracteres'),
  confirm_password: z.string().min(1, 'Confirme a nova senha'),
}).refine(d => d.new_password === d.confirm_password, {
  message: 'As senhas não coincidem',
  path: ['confirm_password'],
})

function ChangePasswordForm({ onCancel }) {
  const mutation = useChangePassword()
  const { register, handleSubmit, formState: { errors }, reset } = useForm({
    resolver: zodResolver(changePasswordSchema),
  })

  const onSubmit = async (data) => {
    await mutation.mutateAsync({
      old_password: data.old_password,
      new_password: data.new_password,
    })
    reset()
    onCancel()
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      style={{
        background: '#0F0F0F',
        border: '1px solid #1E1E1E',
        borderTop: 'none',
        borderRadius: '0 0 16px 16px',
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
      noValidate
    >
      <Input
        type="password"
        label="Senha actual"
        placeholder="••••••••"
        error={errors.old_password?.message}
        {...register('old_password')}
      />
      <Input
        type="password"
        label="Nova senha"
        placeholder="••••••••"
        hint="Mínimo 8 caracteres"
        error={errors.new_password?.message}
        {...register('new_password')}
      />
      <Input
        type="password"
        label="Confirmar nova senha"
        placeholder="••••••••"
        error={errors.confirm_password?.message}
        {...register('confirm_password')}
      />
      <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
        <Button variant="surface" size="md" type="button" onClick={onCancel} style={{ flex: 1 }}>
          Cancelar
        </Button>
        <Button variant="primary" size="md" type="submit" loading={mutation.isPending} style={{ flex: 1 }}>
          Confirmar
        </Button>
      </div>
    </form>
  )
}

export default function SecurityPage() {
  const navigate = useNavigate()
  const logout = useAuth(s => s.logout)
  const [showChangePass, setShowChangePass] = useState(false)

  const ITEMS = [
    {
      icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
      label: 'Alterar senha',
      sub: 'Recomendado a cada 3 meses',
      action: () => setShowChangePass(v => !v),
      color: '#C9A84C',
      hasForm: true,
    },
    {
      icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
      label: 'Autenticação 2 factores',
      sub: 'Adiciona uma camada extra de segurança',
      color: '#3b82f6',
      badge: 'Em breve',
    },
    {
      icon: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
      label: 'Terminar todas as sessões',
      sub: 'Encerra sessão em todos os dispositivos',
      action: () => { logout(); navigate('/login') },
      color: '#ef4444',
    },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <PageHeader title="Privacidade & Segurança" backTo="/profile" />

      <div className="screen" role="main" style={{ flex: 1 }}>
        <div style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 10 }} className="stagger">
          {ITEMS.map((item, i) => (
            <div key={i}>
              <button
                onClick={item.action}
                disabled={!item.action}
                aria-expanded={item.hasForm ? showChangePass : undefined}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 14,
                  padding: '16px', borderRadius: item.hasForm && showChangePass ? '16px 16px 0 0' : 16,
                  cursor: item.action ? 'pointer' : 'default', textAlign: 'left',
                  background: '#141414', border: '1px solid #1E1E1E',
                  transition: 'border-radius 0.15s ease',
                }}
              >
                <div style={{
                  width: 40, height: 40, borderRadius: 12,
                  background: `${item.color}15`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={item.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d={item.icon} />
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <p style={{
                    fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500,
                    color: item.color === '#ef4444' ? '#ef4444' : '#FFFFFF',
                  }}>
                    {item.label}
                  </p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>
                    {item.sub}
                  </p>
                </div>
                {item.badge && <Badge variant="muted">{item.badge}</Badge>}
                {!item.badge && item.action && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d={showChangePass && item.hasForm ? 'M18 15l-6-6-6 6' : 'M9 18l6-6-6-6'} />
                  </svg>
                )}
              </button>

              {item.hasForm && showChangePass && (
                <ChangePasswordForm onCancel={() => setShowChangePass(false)} />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
