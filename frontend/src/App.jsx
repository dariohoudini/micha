import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Suspense, lazy, useEffect } from 'react'
import ErrorBoundary from '@/components/shared/ErrorBoundary'
import SessionGuard from '@/components/shared/SessionGuard'
import MaintenanceGate from '@/components/shared/MaintenanceGate'
import { track } from '@/lib/userTrack'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import OfflineBanner from '@/components/ui/OfflineBanner'
import CookieConsentBanner from '@/components/CookieConsentBanner'
import ImpersonationBanner from '@/components/shared/ImpersonationBanner'
import { usePushNotifications } from '@/hooks/usePushNotifications'
import { attachCartSync } from '@/lib/cartSync'
import { useDeepLinks } from '@/lib/deepLinks'
import { toast } from '@/components/ui/Toast'

// Onboarding
const SplashPage         = lazy(() => import('@/pages/SplashPage'))
const OnboardingCarouselPage = lazy(() => import('@/pages/OnboardingCarouselPage'))
const LanguagePage       = lazy(() => import('@/pages/LanguagePage'))
const WelcomePage        = lazy(() => import('@/pages/WelcomePage'))
const LoginPage          = lazy(() => import('@/pages/LoginPage'))
const RegisterPage       = lazy(() => import('@/pages/RegisterPage'))
const OTPPage            = lazy(() => import('@/pages/OTPPage'))
const ForgotPasswordPage    = lazy(() => import('@/pages/ForgotPasswordPage'))
const ResetPasswordPage     = lazy(() => import('@/pages/ResetPasswordPage'))
const OnboardingQuizPage    = lazy(() => import('@/pages/OnboardingQuizPage'))

// Buyer
const HomePage              = lazy(() => import('@/pages/buyer/HomePage'))
const ExplorePage           = lazy(() => import('@/pages/buyer/ExplorePage'))
const ProductDetailPage     = lazy(() => import('@/pages/buyer/ProductDetailPage'))
const CartPage              = lazy(() => import('@/pages/buyer/CartPage'))
const CheckoutPage          = lazy(() => import('@/pages/buyer/CheckoutPage'))
const OrderConfirmedPage    = lazy(() => import('@/pages/buyer/OrderConfirmedPage'))
const OrdersPage            = lazy(() => import('@/pages/buyer/OrdersPage'))
const WishlistPage          = lazy(() => import('@/pages/buyer/WishlistPage'))
const NotificationsPage     = lazy(() => import('@/pages/buyer/NotificationsPage'))
const ProfilePage           = lazy(() => import('@/pages/buyer/ProfilePage'))
const AddressesPage         = lazy(() => import('@/pages/buyer/AddressesPage'))
const VouchersPage          = lazy(() => import('@/pages/buyer/VouchersPage'))
const LoyaltyPage           = lazy(() => import('@/pages/buyer/LoyaltyPage'))
const SessionsPage          = lazy(() => import('@/pages/buyer/SessionsPage'))
const TwoFactorPage         = lazy(() => import('@/pages/buyer/TwoFactorPage'))
const DeleteAccountPage     = lazy(() => import('@/pages/buyer/DeleteAccountPage'))
const ReturnRequestPage     = lazy(() => import('@/pages/buyer/ReturnRequestPage'))
const FlashSalePage         = lazy(() => import('@/pages/buyer/FlashSalePage'))
const CoinsPage             = lazy(() => import('@/pages/buyer/CoinsPage'))
const CoinGamesPage         = lazy(() => import('@/pages/buyer/CoinGamesPage'))
const LiveStreamsPage       = lazy(() => import('@/pages/buyer/LiveStreamsPage'))
const ReviewWritePage       = lazy(() => import('@/pages/buyer/ReviewWritePage'))
const ProfileEditPage       = lazy(() => import('@/pages/buyer/ProfileEditPage'))
const SecurityPage          = lazy(() => import('@/pages/buyer/SecurityPage'))
const ReferralPage          = lazy(() => import('@/pages/buyer/ReferralPage'))
const ChatPage              = lazy(() => import('@/pages/buyer/ChatPage'))
const ChatConversationPage  = lazy(() => import('@/pages/buyer/ChatConversationPage'))
const StorePage             = lazy(() => import('@/pages/buyer/StorePage'))
const OrderDetailPage       = lazy(() => import('@/pages/buyer/OrderDetailPage'))
const DisputeFilingPage     = lazy(() => import('@/pages/buyer/DisputeFilingPage'))

// Seller
const SellerDashboardPage   = lazy(() => import('@/pages/seller/SellerDashboardPage'))
const SellerProductsPage    = lazy(() => import('@/pages/seller/SellerProductsPage'))
const SellerProductNewPage  = lazy(() => import('@/pages/seller/SellerProductNewPage'))
const SellerProductEditPage = lazy(() => import('@/pages/seller/SellerProductEditPage'))
const SellerOrdersPage      = lazy(() => import('@/pages/seller/SellerOrdersPage'))
const SellerWalletPage      = lazy(() => import('@/pages/seller/SellerWalletPage'))
const SellerSetupPage       = lazy(() => import('@/pages/seller/SellerSetupPage'))
const SellerMyStorePage     = lazy(() => import('@/pages/seller/SellerMyStorePage'))
const SellerOnboardingPage  = lazy(() => import('@/pages/seller/SellerOnboardingPage'))
const SellerApplicationStatusPage = lazy(() => import('@/pages/seller/SellerApplicationStatusPage'))
const SellerShippingTemplatesPage = lazy(() => import('@/pages/seller/SellerShippingTemplatesPage'))
const SellerBusinessAdvisorPage = lazy(() => import('@/pages/seller/SellerBusinessAdvisorPage'))
const SellerChoicePage      = lazy(() => import('@/pages/seller/SellerChoicePage'))
const SellerAnalyticsPage   = lazy(() => import('@/pages/seller/SellerAnalyticsPage'))
const SellerChatPage        = lazy(() => import('@/pages/seller/SellerChatPage'))

// Rentals
const RentalsPage           = lazy(() => import('@/pages/buyer/rentals/RentalsPage'))
const RentalDetailPage      = lazy(() => import('@/pages/buyer/rentals/RentalDetailPage'))
const CreateRentalPage      = lazy(() => import('@/pages/rentals/CreateListingPage'))
const VerificationGatePage  = lazy(() => import('@/pages/verification/VerificationGatePage'))
const MonthlySelfieGatePage = lazy(() => import('@/pages/verification/MonthlySelfieGatePage'))

// Admin
const AdminDashboardPage    = lazy(() => import('@/pages/admin/AdminDashboardPage'))
const AdminUsersPage        = lazy(() => import('@/pages/admin/AdminUsersPage'))
const AdminOrdersPage       = lazy(() => import('@/pages/admin/AdminOrdersPage'))
const AdminSellersPage      = lazy(() => import('@/pages/admin/AdminSellersPage'))
const AdminProductsPage     = lazy(() => import('@/pages/admin/AdminProductsPage'))
const AdminSettingsPage     = lazy(() => import('@/pages/admin/AdminSettingsPage'))
const AdminChatPage         = lazy(() => import('@/pages/admin/AdminChatPage'))
const AdminFraudPage        = lazy(() => import('@/pages/admin/AdminFraudPage'))
const AdminMonitoringPage   = lazy(() => import('@/pages/admin/AdminMonitoringPage'))
const AdminOpsQueuePage     = lazy(() => import('@/pages/admin/AdminOpsQueuePage'))
const AdminModerationQueuePage = lazy(() => import('@/pages/admin/AdminModerationQueuePage'))
const AdminChargebacksPage  = lazy(() => import('@/pages/admin/AdminChargebacksPage'))
const AdminAMLPage          = lazy(() => import('@/pages/admin/AdminAMLPage'))
const SellerDashboardR7Page = lazy(() => import('@/pages/seller/SellerDashboardR7Page'))
const AdminCommandCenterPage = lazy(() => import('@/pages/admin/AdminCommandCenterPage'))
const AdminBroadcastPage    = lazy(() => import('@/pages/admin/AdminBroadcastPage'))

function PageLoader() {
  return (
    <div
      role="status"
      aria-label="A carregar"
      style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A', gap: 16 }}
    >
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
        <circle cx="12" cy="12" r="10" stroke="#C9A84C" strokeWidth="2" strokeOpacity="0.15" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#555' }}>
        A carregar…
      </span>
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { isAuth, loading } = useAuthStore()
  const location = useLocation()
  if (loading) return <PageLoader />
  if (isAuth) return children
  // §34.3 — Return Navigation Logic. Stash where the guest was going
  // so LoginPage can replay the navigation (and any pending action)
  // after successful login/registration. Without this state, the
  // user who deep-linked into /cart, /checkout, /orders/:id etc.
  // would be bounced to /home after login and lose context.
  return (
    <Navigate
      to="/login"
      replace
      state={{
        returnTo: location.pathname + (location.search || ''),
        returnAction: 'navigate',
        returnParams: {},
      }}
    />
  )
}

function SellerRoute({ children }) {
  // SECURITY: defence-in-depth. The backend enforces role authorization
  // on every API endpoint via IsSellerOrSuperuser / IsAdminOrSuperuser
  // permission classes — that's the AUTHORITATIVE check. This component
  // only gates UI rendering so honest users don't see broken seller UI
  // before the API rejects their first call.
  //
  // PRIOR BUG: these checks were commented out with the note
  // "Temporarily allow all auth users — remove when JWT is fixed",
  // which let any authenticated buyer navigate to /seller/* and
  // attempt seller actions. The backend permission classes still
  // blocked the actual API calls, but: (a) the broken UI was a real
  // CX bug, (b) any endpoint with weakly-enforced authz on the
  // backend was newly reachable.
  const { isAuth, isSeller, isStaff, loading } = useAuthStore()
  if (loading) return <PageLoader />
  if (!isAuth) return <Navigate to="/login" replace />
  // Sellers AND admins (staff can act on behalf of sellers for support).
  if (!isSeller && !isStaff) return <Navigate to="/home" replace />
  return children
}

function AdminRoute({ children }) {
  // SECURITY: defence-in-depth (see SellerRoute comment).
  // Admin routes must be staff-only.
  const { isAuth, isStaff, loading } = useAuthStore()
  if (loading) return <PageLoader />
  if (!isAuth) return <Navigate to="/login" replace />
  if (!isStaff) return <Navigate to="/home" replace />
  return children
}

function RoleRedirect() {
  const { isAuth, isStaff, loading } = useAuthStore()
  if (loading) return <PageLoader />
  if (!isAuth) return <Navigate to="/login" replace />
  if (isStaff) return <Navigate to="/admin" replace />
  return <Navigate to="/home" replace />
}

const P = ({ children }) => <ProtectedRoute>{children}</ProtectedRoute>
const S = ({ children }) => <SellerRoute>{children}</SellerRoute>
const A = ({ children }) => <AdminRoute>{children}</AdminRoute>

function GlobalSetup() {
  const setOnline = useUIStore(s => s.setOnline)
  const isAuth = useAuthStore(s => s.isAuth)
  const user = useAuthStore(s => s.user)
  const location = useLocation()
  const navigate = useNavigate()

  // §34.4 — Navigation Stack Reset listener. The auth store fires
  // `micha:auth-stack-reset` from outside the router (sign-out,
  // banned, forced-update, onboarding-complete). We translate that
  // to a real `navigate(to, { replace: true })` here so the React
  // tree actually unmounts the previous root and the user can't
  // ⌫-back into authenticated screens after sign-out.
  useEffect(() => {
    const onReset = (e) => {
      const to = (e && e.detail && e.detail.to) || '/login'
      navigate(to, { replace: true })
    }
    window.addEventListener('micha:auth-stack-reset', onReset)
    return () => window.removeEventListener('micha:auth-stack-reset', onReset)
  }, [navigate])

  // User Process Flow §20.8 — log every navigation to the DB.
  // Single source of truth: every screen the user lands on writes
  // a `route.view` row into UserEvent via the batched track API.
  useEffect(() => {
    track('route.view', {
      path: location.pathname,
      search: location.search || undefined,
      user_id: user?.id || undefined,
    })
  }, [location.pathname, location.search, user?.id])

  // Log launch + auth state transitions exactly once per boot.
  useEffect(() => { track('app.open', {}) }, [])
  useEffect(() => {
    track(isAuth ? 'auth.session_active' : 'auth.session_anonymous',
          { user_id: user?.id || null })
  }, [isAuth, user?.id])
  usePushNotifications({
    onNotification: (notification) => {
      const title = notification.title || 'MICHA'
      const body = notification.body || ''
      toast.success(body ? `${title}: ${body}` : title, { duration: 5000 })
    },
  })
  // R5-C: universal-link / app-link route handler. Subscribes to
  // Capacitor's appUrlOpen event and forwards into react-router.
  // No-op on web builds.
  useDeepLinks()

  // R5-B: attach the offline-aware cart sync engine. Re-runs when
  // ``isAuth`` flips so that login immediately triggers a /merge/
  // of the anonymous local cart into the user's server cart —
  // closing the "I added 5 items as a guest then signed in and they
  // disappeared" bug that bounced buyers in early testing.
  useEffect(() => {
    const cleanup = attachCartSync()
    return cleanup
  }, [isAuth])

  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)

    const onUnhandled = (e) => {
      e.preventDefault()
      console.error('[MICHA] Unhandled rejection:', e.reason)
    }
    window.addEventListener('unhandledrejection', onUnhandled)

    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
      window.removeEventListener('unhandledrejection', onUnhandled)
    }
  }, [setOnline])

  return null
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <GlobalSetup />
        <SessionGuard />
        <MaintenanceGate />
        <a href="#main-content" className="skip-link">
          Saltar para o conteúdo principal
        </a>
        <OfflineBanner />
        <CookieConsentBanner />
        <ImpersonationBanner />
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Onboarding */}
            <Route path="/"                element={<SplashPage />} />
            <Route path="/onboarding/carousel" element={<OnboardingCarouselPage />} />
            <Route path="/language"        element={<LanguagePage />} />
            <Route path="/welcome"         element={<WelcomePage />} />
            <Route path="/login"           element={<LoginPage />} />
            <Route path="/register"        element={<RegisterPage />} />
            <Route path="/otp"             element={<OTPPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password"  element={<ResetPasswordPage />} />
            <Route path="/onboarding/quiz" element={<P><OnboardingQuizPage /></P>} />
            <Route path="/dashboard"       element={<RoleRedirect />} />

            {/* ── Buyer ── */}
            <Route path="/home"                element={<P><HomePage /></P>} />
            <Route path="/explore"             element={<P><ExplorePage /></P>} />
            <Route path="/product/:id"         element={<P><ProductDetailPage /></P>} />
            <Route path="/cart"                element={<P><CartPage /></P>} />
            <Route path="/checkout"            element={<P><CheckoutPage /></P>} />
            <Route path="/order-confirmed"     element={<P><OrderConfirmedPage /></P>} />
            <Route path="/orders"              element={<P><OrdersPage /></P>} />
            <Route path="/wishlist"            element={<P><WishlistPage /></P>} />
            <Route path="/notifications"       element={<P><NotificationsPage /></P>} />
            <Route path="/profile"             element={<P><ProfilePage /></P>} />
            <Route path="/profile/edit"        element={<P><ProfileEditPage /></P>} />
            <Route path="/profile/addresses"   element={<P><AddressesPage /></P>} />
            <Route path="/profile/vouchers"    element={<P><VouchersPage /></P>} />
            <Route path="/profile/loyalty"     element={<P><LoyaltyPage /></P>} />
            <Route path="/profile/sessions"    element={<P><SessionsPage /></P>} />
            <Route path="/profile/2fa"         element={<P><TwoFactorPage /></P>} />
            <Route path="/profile/delete"      element={<P><DeleteAccountPage /></P>} />
            <Route path="/orders/:orderId/return" element={<P><ReturnRequestPage /></P>} />
            <Route path="/flash-sale"          element={<P><FlashSalePage /></P>} />
            <Route path="/coins"               element={<P><CoinsPage /></P>} />
            <Route path="/coins/games"         element={<P><CoinGamesPage /></P>} />
            <Route path="/live"                element={<P><LiveStreamsPage /></P>} />
            <Route path="/orders/:orderId/review" element={<P><ReviewWritePage /></P>} />
            <Route path="/security"            element={<P><SecurityPage /></P>} />
            <Route path="/referral"            element={<P><ReferralPage /></P>} />
            <Route path="/chat"                element={<P><ChatPage /></P>} />
            <Route path="/chat/:id"            element={<P><ChatConversationPage /></P>} />
            <Route path="/store/:id"           element={<P><StorePage /></P>} />
            <Route path="/orders/:id"          element={<P><OrderDetailPage /></P>} />
            <Route path="/dispute/:orderId"    element={<P><DisputeFilingPage /></P>} />

            {/* ── Rentals ── */}
            <Route path="/rentals"             element={<P><RentalsPage /></P>} />
            <Route path="/rentals/:id"         element={<P><RentalDetailPage /></P>} />
            <Route path="/rentals/new"         element={<P><CreateRentalPage /></P>} />
            <Route path="/verify/kyc"          element={<P><VerificationGatePage /></P>} />
            <Route path="/verify/selfie"       element={<P><MonthlySelfieGatePage /></P>} />

            {/* ── Seller ── */}
            <Route path="/seller"              element={<S><SellerDashboardPage /></S>} />
            <Route path="/seller/products"              element={<S><SellerProductsPage /></S>} />
            <Route path="/seller/products/new"          element={<S><SellerProductNewPage /></S>} />
            <Route path="/seller/products/:id/edit"     element={<S><SellerProductEditPage /></S>} />
            <Route path="/seller/orders"       element={<S><SellerOrdersPage /></S>} />
            <Route path="/seller/wallet"       element={<S><SellerWalletPage /></S>} />
            <Route path="/seller/setup"        element={<S><SellerSetupPage /></S>} />
            <Route path="/seller/store"        element={<S><SellerMyStorePage /></S>} />
            <Route path="/seller/onboarding"   element={<S><SellerOnboardingPage /></S>} />
            <Route path="/seller/application"  element={<S><SellerApplicationStatusPage /></S>} />
            <Route path="/seller/shipping"     element={<S><SellerShippingTemplatesPage /></S>} />
            <Route path="/seller/business-advisor" element={<S><SellerBusinessAdvisorPage /></S>} />
            <Route path="/seller/choice"       element={<S><SellerChoicePage /></S>} />
            <Route path="/seller/analytics"    element={<S><SellerAnalyticsPage /></S>} />
            <Route path="/seller/chat"         element={<S><SellerChatPage /></S>} />

            {/* ── Admin ── */}
            <Route path="/admin"               element={<A><AdminDashboardPage /></A>} />
            <Route path="/admin/users"         element={<A><AdminUsersPage /></A>} />
            <Route path="/admin/orders"        element={<A><AdminOrdersPage /></A>} />
            <Route path="/admin/sellers"       element={<A><AdminSellersPage /></A>} />
            <Route path="/admin/products"      element={<A><AdminProductsPage /></A>} />
            <Route path="/admin/settings"      element={<A><AdminSettingsPage /></A>} />
            <Route path="/admin/chat"          element={<A><AdminChatPage /></A>} />
            <Route path="/admin/fraud"         element={<A><AdminFraudPage /></A>} />
            <Route path="/admin/monitoring"    element={<A><AdminMonitoringPage /></A>} />
            <Route path="/admin/ops"           element={<A><AdminOpsQueuePage /></A>} />
            <Route path="/admin/moderation"    element={<A><AdminModerationQueuePage /></A>} />
            <Route path="/admin/chargebacks"   element={<A><AdminChargebacksPage /></A>} />
            <Route path="/admin/aml"           element={<A><AdminAMLPage /></A>} />
            <Route path="/seller/analytics-r7" element={<S><SellerDashboardR7Page /></S>} />
            <Route path="/admin/command-center" element={<A><AdminCommandCenterPage /></A>} />
            <Route path="/admin/broadcast"     element={<A><AdminBroadcastPage /></A>} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
