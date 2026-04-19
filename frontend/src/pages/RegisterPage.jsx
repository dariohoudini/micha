import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { registerSchema } from '@/lib/validation'
import { authAPI } from '@/api/auth'
import { toast } from '@/components/ui/Toast'
import { FormField, Input, PhoneInput, ErrorBanner } from '@/components/ui/FormField'
import { FadeIn } from '@/components/ui/PageTransition'

export default function RegisterPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    trigger,
    watch,
    setValue,
    formState: { errors, isSubmitting },
    setError,
  } = useForm({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: '', username: '', full_name: '', phone: '',
      password: '', password2: '',
      account_type: 'buyer',
      privacy_consent: false,
      terms_consent: false,
    },
  })

  const accountType = watch('account_type')
  const privacyConsent = watch('privacy_consent')
  const termsConsent = watch('terms_consent')

  const handleNext = async () => {
    const valid = await trigger(['email', 'username', 'full_name', 'phone', 'account_type'])
    if (valid) setStep(2)
  }

  const onSubmit = async (data) => {
    try {
      await authAPI.register({
        email: data.email,
        username: data.username,
        full_name: data.full_name || undefined,
        phone: data.phone ? `+244${data.phone}` : undefined,
        password: data.password,
        password2: data.password2,
        privacy_consent: data.privacy_consent,
        terms_consent: data.terms_consent,
        account_type: data.account_type,
      })
      toast.success('Conta criada! Verifique o seu email.')
      navigate('/otp', { state: { email: data.email, context: 'register' } })
    } catch (err) {
      const errData = err.response?.data
      if (errData?.field_errors) {
        Object.entries(errData.field_errors).forEach(([field, msgs]) => {
          setError(field, { message: Array.isArray(msgs) ? msgs[0] : msgs })
        })
        if (Object.keys(errData.field_errors).some(f => ['email', 'username', 'phone'].includes(f))) {
          setStep(1)
        }
      } else {
        setError('root', { message: errData?.detail || t('errors.generic') })
      }
    }
  }

  const Label = ({ children }) => (
    <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
      {children}
    </label>
  )

  return (
    <div className="screen" style={{ minHeight: '100%', background: '#0A0A0A', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: 'linear-gradient(90deg, #C9A84C, #E2C47A, #C9A84C)' }} />

      <div style={{ padding: '20px 24px 0', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          type="button"
          onClick={() => step === 2 ? setStep(1) : navigate('/login')}
          aria-label={t('common.back')}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
        <div>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>
            {step === 1 ? t('auth.register') : 'Segurança'}
          </h1>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>
            {t('auth.step', { current: step, total: 2 })}
          </p>
        </div>
      </div>

      {/* Progress */}
      <div role="progressbar" aria-valuenow={step} aria-valuemin={1} aria-valuemax={2} aria-label="Progresso do registo"
        style={{ margin: '16px 24px 0', height: 3, background: '#1E1E1E', borderRadius: 2 }}>
        <div style={{ height: '100%', borderRadius: 2, background: '#C9A84C', width: step === 1 ? '50%' : '100%', transition: 'width 0.4s ease' }} />
      </div>

      <form onSubmit={handleSubmit(onSubmit)} noValidate style={{ padding: '24px 24px 0', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ErrorBanner message={errors.root?.message} />

        {step === 1 ? (
          <FadeIn style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <FormField label="Nome completo" error={errors.full_name?.message} htmlFor="full_name">
              <Input id="full_name" placeholder="João Silva" autoComplete="name" {...register('full_name')} />
            </FormField>

            <FormField label={t('auth.email')} error={errors.email?.message} htmlFor="email" required>
              <Input id="email" type="email" placeholder="o.seu@email.com" autoCapitalize="none" autoComplete="email" error={errors.email?.message} {...register('email')} />
            </FormField>

            <FormField label={t('auth.username')} error={errors.username?.message} htmlFor="username" required hint="Apenas letras minúsculas, números e _">
              <Input id="username" placeholder="joaosilva" autoCapitalize="none" autoComplete="username" error={errors.username?.message} {...register('username')} />
            </FormField>

            <FormField label={t('auth.phone')} error={errors.phone?.message} htmlFor="phone">
              <PhoneInput id="phone" placeholder="9xx xxx xxx" error={errors.phone?.message} {...register('phone')} />
            </FormField>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Label>{t('auth.accountType')}</Label>
              <div role="group" aria-label="Tipo de conta" style={{ display: 'flex', gap: 10 }}>
                {[{ value: 'buyer', label: t('auth.buyer') }, { value: 'seller', label: t('auth.seller') }].map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={accountType === opt.value}
                    onClick={() => setValue('account_type', opt.value)}
                    style={{
                      flex: 1, padding: '12px 0', borderRadius: 12, cursor: 'pointer',
                      border: `1.5px solid ${accountType === opt.value ? '#C9A84C' : '#2A2A2A'}`,
                      background: accountType === opt.value ? 'rgba(201,168,76,0.1)' : '#141414',
                      fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600,
                      color: accountType === opt.value ? '#C9A84C' : '#9A9A9A',
                      transition: 'all 0.2s',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <button type="button" className="btn-primary" onClick={handleNext} style={{ marginTop: 8 }}>
              {t('common.next')}
            </button>
          </FadeIn>
        ) : (
          <FadeIn style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <FormField label={t('auth.password')} error={errors.password?.message} htmlFor="password" required>
              <div style={{ position: 'relative' }}>
                <Input id="password" type={showPassword ? 'text' : 'password'} placeholder="Mínimo 8 caracteres" autoComplete="new-password" error={errors.password?.message} style={{ paddingRight: 48 }} {...register('password')} />
                <button type="button" onClick={() => setShowPassword(v => !v)} aria-label={showPassword ? 'Esconder' : 'Mostrar'}
                  style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={showPassword ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                  </svg>
                </button>
              </div>
            </FormField>

            <FormField label={t('auth.confirmPassword')} error={errors.password2?.message} htmlFor="password2" required>
              <Input id="password2" type="password" placeholder="••••••••" autoComplete="new-password" error={errors.password2?.message} {...register('password2')} />
            </FormField>

            {/* Consent checkboxes */}
            <fieldset style={{ border: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <legend style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#9A9A9A', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 8 }}>
                Consentimentos obrigatórios
              </legend>

              {[
                { field: 'privacy_consent', value: privacyConsent, text: t('auth.privacyConsent') },
                { field: 'terms_consent', value: termsConsent, text: t('auth.termsConsent') },
              ].map(({ field, value, text }) => (
                <label key={field} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', cursor: 'pointer' }}>
                  <div
                    role="checkbox"
                    aria-checked={value}
                    tabIndex={0}
                    onClick={() => setValue(field, !value, { shouldValidate: true })}
                    onKeyDown={e => e.key === ' ' && setValue(field, !value, { shouldValidate: true })}
                    style={{
                      width: 20, height: 20, borderRadius: 5, flexShrink: 0, marginTop: 2,
                      border: `2px solid ${value ? '#C9A84C' : errors[field] ? '#dc2626' : '#2A2A2A'}`,
                      background: value ? '#C9A84C' : 'transparent',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'all 0.2s', cursor: 'pointer',
                    }}
                  >
                    {value && <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6l3 3 5-5" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}
                  </div>
                  <input type="checkbox" {...register(field)} style={{ display: 'none' }} />
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', lineHeight: 1.5 }}>{text}</span>
                </label>
              ))}

              {(errors.privacy_consent || errors.terms_consent) && (
                <p role="alert" style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>
                  {errors.privacy_consent?.message || errors.terms_consent?.message}
                </p>
              )}
            </fieldset>

            <button type="submit" className="btn-primary" disabled={isSubmitting} aria-busy={isSubmitting} style={{ marginTop: 8, opacity: isSubmitting ? 0.7 : 1 }}>
              {isSubmitting ? t('common.loading') : t('auth.register')}
            </button>
          </FadeIn>
        )}
      </form>

      <p style={{ padding: '20px 24px 36px', textAlign: 'center' }}>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{t('auth.hasAccount')} </span>
        <button type="button" onClick={() => navigate('/login')} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>
          {t('auth.login')}
        </button>
      </p>
    </div>
  )
}
