import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate, Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { loginSchema } from '@/lib/validation'
import { useAuthStore } from '@/stores/authStore'
import { authAPI, profileAPI } from '@/api/auth'
import { toast } from '@/components/ui/Toast'
import { FormField, Input, ErrorBanner } from '@/components/ui/FormField'
import { FadeIn } from '@/components/ui/PageTransition'
import { consumeReturnAction } from '@/lib/authGate'

export default function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore(s => s.login)
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  const onSubmit = async (data) => {
    try {
      const res = await authAPI.login(data.email, data.password)

      // The backend's MyTokenObtainPairSerializer returns ONLY
      // {access, refresh} — no user object. Previously the FE fell
      // back to `{ email }` here, which meant `is_seller` and
      // `is_staff` were never populated → SellerRoute / AdminRoute
      // saw `isSeller: false` for actual sellers and bounced them
      // back to /home. Bug: registered sellers could only see the
      // buyer UI and had no way to upload or manage products.
      //
      // Fix: stash the tokens (so the next request is authenticated),
      // then GET /auth/profile/ to load the full UserSerializer
      // payload (which includes is_seller / is_verified_seller /
      // is_staff), and only THEN finalise the auth store + navigate.
      login({ email: data.email }, {
        access: res.data.access,
        refresh: res.data.refresh,
      })
      try {
        // NOTE: getProfile lives on `profileAPI`, not `authAPI`. A
        // prior version of this code called `authAPI.getProfile()`
        // which is `undefined` → TypeError → caught here silently →
        // isSeller stayed false → every seller landed on the buyer
        // home. Don't re-introduce that mistake.
        const profile = await profileAPI.getProfile()
        useAuthStore.getState().updateUser(profile.data)
      } catch {
        // Profile fetch failed — fall through with minimal user.
        // Buyer UI still works; seller will need to re-login or
        // refresh. Better than blocking login on a flaky /profile/.
      }

      toast.success('Bem-vindo de volta!')
      // §34.3 — Return Navigation Logic. If the user landed on the
      // login screen because they tapped a gated button (add-to-cart
      // on a PDP, "Follow Seller", deep-link into /cart, etc.) we
      // replay the original action and return them to that screen
      // instead of dropping them on /home with no context.
      const returnTo = await consumeReturnAction(location.state)
      if (returnTo) {
        navigate(returnTo, { replace: true })
      } else {
        // Route by role: staff → /admin, seller → /seller, else /home.
        const { isStaff, isSeller } = useAuthStore.getState()
        if (isStaff) navigate('/admin', { replace: true })
        else if (isSeller) navigate('/seller', { replace: true })
        else navigate('/home', { replace: true })
      }
    } catch (err) {
      const detail = err.response?.data?.detail || t('errors.generic')
      setError('root', { message: detail })
    }
  }

  return (
    <div className="screen" style={{ minHeight: '100%', background: '#0A0A0A', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: 'linear-gradient(90deg, #C9A84C, #E2C47A, #C9A84C)' }} />

      <FadeIn style={{ padding: '40px 24px 32px' }}>
        <div style={{ marginBottom: 32 }}>
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#C9A84C' }}>MICHA</span>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#E2C47A', letterSpacing: '0.2em', marginLeft: 6 }}>EXPRESS</span>
        </div>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 30, fontWeight: 700, color: '#FFFFFF', lineHeight: 1.2, marginBottom: 8 }}>
          {t('auth.welcomeBack')}
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>
          {t('auth.loginSubtitle')}
        </p>
      </FadeIn>

      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        style={{ padding: '0 24px', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}
      >
        <ErrorBanner message={errors.root?.message} />

        <FormField label={t('auth.email')} error={errors.email?.message} htmlFor="email" required>
          <Input
            id="email"
            type="email"
            placeholder="o.seu@email.com"
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="email"
            error={errors.email?.message}
            {...register('email')}
          />
        </FormField>

        <FormField label={t('auth.password')} error={errors.password?.message} htmlFor="password" required>
          <div style={{ position: 'relative' }}>
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••••"
              autoComplete="current-password"
              error={errors.password?.message}
              style={{ paddingRight: 48 }}
              {...register('password')}
            />
            <button
              type="button"
              onClick={() => setShowPassword(v => !v)}
              aria-label={showPassword ? 'Esconder palavra-passe' : 'Mostrar palavra-passe'}
              style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke={showPassword ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {showPassword
                  ? <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><line x1="1" y1="1" x2="23" y2="23" /></>
                  : <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>
                }
              </svg>
            </button>
          </div>
        </FormField>

        <div style={{ textAlign: 'right' }}>
          <Link to="/forgot-password" style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#C9A84C', textDecoration: 'none' }}>
            {t('auth.forgotPassword')}
          </Link>
        </div>

        <button
          type="submit"
          className="btn-primary"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
          style={{ marginTop: 8, opacity: isSubmitting ? 0.7 : 1 }}
        >
          {isSubmitting ? t('common.loading') : t('auth.login')}
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0' }}>
          <div style={{ flex: 1, height: 1, background: '#2A2A2A' }} />
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>ou</span>
          <div style={{ flex: 1, height: 1, background: '#2A2A2A' }} />
        </div>

        <Link to="/register" style={{ textDecoration: 'none' }}>
          <button type="button" className="btn-secondary" style={{ width: '100%' }}>
            {t('auth.register')}
          </button>
        </Link>
      </form>

      <p style={{ padding: '24px', textAlign: 'center', fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', lineHeight: 1.6 }}>
        Ao continuar aceita os nossos{' '}
        <span style={{ color: '#C9A84C' }}>Termos de Uso</span>
        {' '}e{' '}
        <span style={{ color: '#C9A84C' }}>Política de Privacidade</span>
      </p>
    </div>
  )
}
