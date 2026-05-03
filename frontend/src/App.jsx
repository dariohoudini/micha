import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy, useEffect } from 'react'
import ErrorBoundary from '@/components/shared/ErrorBoundary'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import OfflineBanner from '@/components/ui/OfflineBanner'
import { usePushNotifications } from '@/hooks/usePushNotifications'
import { toast } from '@/components/ui/Toast'

// Onboarding
const SplashPage         = lazy(() => import('@/pages/SplashPage'))
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
  if (loading) return <PageLoader />
  return isAuth ? children : <Navigate to="/login" replace />
}

function SellerRoute({ children }) {
  const { isAuth, isSeller, isStaff, loading } = useAuthStore()
  if (loading) return <PageLoader />
  if (!isAuth) return <Navigate to="/login" replace />
  // Temporarily allow all auth users — remove when JWT is fixed
  return children
}

function AdminRoute({ children }) {
  const { isAuth, isStaff, loading } = useAuthStore()
  if (loading) return <PageLoader />
  if (!isAuth) return <Navigate to="/login" replace />
  // Temporarily allow all auth users — remove when JWT is fixed
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
  usePushNotifications({
    onNotification: (notification) => {
      const title = notification.title || 'MICHA'
      const body = notification.body || ''
      toast.success(body ? `${title}: ${body}` : title, { duration: 5000 })
    },
  })

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
        <a href="#main-content" className="skip-link">
          Saltar para o conteúdo principal
        </a>
        <OfflineBanner />
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Onboarding */}
            <Route path="/"                element={<SplashPage />} />
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

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
