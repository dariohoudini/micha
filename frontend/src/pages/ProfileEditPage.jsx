import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuthStore as useAuth } from '@/stores/authStore'
import { useProfile, useUpdateProfile } from '@/hooks/useQueries'
import PageHeader from '@/components/ui/PageHeader'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'
import Avatar from '@/components/ui/Avatar'

const schema = z.object({
  full_name: z.string().optional(),
  username: z.string().min(3, 'Mínimo 3 caracteres').max(30).regex(/^[a-z0-9_]+$/, 'Apenas letras minúsculas, números e _').optional().or(z.literal('')),
  phone: z.string().optional(),
  city: z.string().optional(),
  bio: z.string().max(200, 'Máximo 200 caracteres').optional(),
})

export default function ProfileEditPage() {
  const navigate = useNavigate()
  const user = useAuth(s => s.user)
  const { data: profile, isLoading } = useProfile()
  const mutation = useUpdateProfile()

  const { register, handleSubmit, reset, watch, formState: { errors, isDirty } } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', username: '', phone: '', city: '', bio: '' },
  })

  // Populate form once profile loads
  useEffect(() => {
    if (profile) {
      reset({
        full_name: profile.full_name || '',
        username: profile.username || '',
        phone: profile.phone || '',
        city: profile.city || '',
        bio: profile.bio || '',
      })
    }
  }, [profile, reset])

  const onSubmit = async (data) => {
    const cleaned = Object.fromEntries(Object.entries(data).filter(([, v]) => v !== ''))
    await mutation.mutateAsync(cleaned)
    navigate('/profile')
  }

  const bioValue = watch('bio') || ''

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <PageHeader title="Editar perfil" backTo="/profile" />

      <div className="screen" role="main" style={{ flex: 1 }}>
        <form
          onSubmit={handleSubmit(onSubmit)}
          style={{ padding: '0 16px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}
          noValidate
        >
          {/* Avatar */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 0 16px' }}>
            <div style={{ position: 'relative' }}>
              <Avatar
                src={profile?.avatar_url}
                name={profile?.full_name}
                email={user?.email}
                size="2xl"
              />
              <button
                type="button"
                aria-label="Alterar foto de perfil"
                style={{
                  position: 'absolute', bottom: 0, right: 0,
                  width: 28, height: 28, borderRadius: '50%',
                  background: '#C9A84C', border: '2px solid #0A0A0A',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
              </button>
            </div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 10 }}>
              Toque para alterar a foto
            </p>
          </div>

          {/* Email — read-only */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Email
            </label>
            <div style={{ padding: '12px 16px', borderRadius: 12, background: '#141414', border: '1px solid #1E1E1E' }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>
                {user?.email}
              </span>
            </div>
          </div>

          <Input
            label="Nome completo"
            optional
            placeholder="João Silva"
            error={errors.full_name?.message}
            disabled={isLoading}
            {...register('full_name')}
          />

          <Input
            label="Username"
            placeholder="joaosilva"
            error={errors.username?.message}
            hint="Apenas letras minúsculas, números e _"
            disabled={isLoading}
            autoCapitalize="none"
            autoCorrect="off"
            {...register('username')}
          />

          {/* Phone with prefix */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Telefone <span style={{ color: '#555', fontWeight: 400, textTransform: 'none', fontSize: 11 }}>(opcional)</span>
            </label>
            <div style={{ display: 'flex' }}>
              <div style={{
                display: 'flex', alignItems: 'center', padding: '0 14px',
                background: '#1E1E1E', border: '1px solid #2A2A2A',
                borderRight: 'none', borderRadius: '12px 0 0 12px',
                fontFamily: "'DM Sans', sans-serif", fontSize: 14,
                color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap',
              }}>
                🇦🇴 +244
              </div>
              <input
                className="input-base"
                type="tel"
                placeholder="9xx xxx xxx"
                style={{ borderRadius: '0 12px 12px 0', flex: 1 }}
                {...register('phone')}
              />
            </div>
          </div>

          <Input
            label="Cidade"
            optional
            placeholder="Luanda"
            error={errors.city?.message}
            disabled={isLoading}
            {...register('city')}
          />

          {/* Bio */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Bio <span style={{ color: '#555', fontWeight: 400, textTransform: 'none', fontSize: 11 }}>(opcional)</span>
              </label>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: bioValue.length > 180 ? '#ef4444' : '#555' }}>
                {bioValue.length}/200
              </span>
            </div>
            <textarea
              className="input-base"
              placeholder="Conte um pouco sobre si…"
              rows={3}
              style={{ resize: 'none', lineHeight: 1.6 }}
              aria-describedby="bio-count"
              {...register('bio')}
            />
            {errors.bio && (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#ef4444' }} role="alert">
                {errors.bio.message}
              </p>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            size="full"
            loading={mutation.isPending}
            disabled={!isDirty && !isLoading}
            style={{ marginTop: 8 }}
          >
            Guardar alterações
          </Button>
        </form>
      </div>
    </div>
  )
}
