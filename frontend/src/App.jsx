import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import ErrorBoundary from '@/components/shared/ErrorBoundary'
import { useAuthStore } from '@/stores/authStore'

// Onboarding
const SplashPage         = lazy(() => import('@/pages/SplashPage'))
const LanguagePage       = lazy(() => import('@/pages/LanguagePage'))
const WelcomePage        = lazy(() => import('@/pages/WelcomePage'))
const LoginPage          = lazy(() => import('@/pages/LoginPage'))
const RegisterPage       = lazy(() => import('@/pages/RegisterPage'))
const OTPPage            = lazy(() => import('@/pages/OTPPage'))
const ForgotPasswordPage = lazy(() => import('@/pages/ForgotPasswordPage'))

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

// Seller
const SellerDashboardPage   = lazy(() => import('@/pages/seller/SellerDashboardPage'))
const SellerProductsPage    = lazy(() => import('@/pages/seller/SellerProductsPage'))
const SellerProductNewPage  = lazy(() => import('@/pages/seller/SellerProductNewPage'))
const SellerOrdersPage      = lazy(() => import('@/pages/seller/SellerOrdersPage'))
const SellerWalletPage      = lazy(() => import('@/pages/seller/SellerWalletPage'))
const SellerSetupPage       = lazy(() => import('@/pages/seller/SellerSetupPage'))
const SellerAnalyticsPage   = lazy(() => import('@/pages/seller/SellerAnalyticsPage'))
const SellerChatPage        = lazy(() => import('@/pages/seller/SellerChatPage'))

// Admin
const AdminDashboardPage    = lazy(() => import('@/pages/admin/AdminDashboardPage'))
const AdminUsersPage        = lazy(() => import('@/pages/admin/AdminUsersPage'))
const AdminOrdersPage       = lazy(() => import('@/pages/admin/AdminOrdersPage'))
const AdminSellersPage      = lazy(() => import('@/pages/admin/AdminSellersPage'))
const AdminProductsPage     = lazy(() => import('@/pages/admin/AdminProductsPage'))
const AdminSettingsPage     = lazy(() => import('@/pages/admin/AdminSettingsPage'))
const AdminChatPage         = lazy(() => import('@/pages/admin/AdminChatPage'))

function PageLoader() {
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0A0A0A' }}>
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <circle cx="12" cy="12" r="10" stroke="#C9A84C" strokeWidth="2" strokeOpacity="0.2" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" />
      </svg>
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

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
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

            {/* ── Seller ── */}
            <Route path="/seller"              element={<S><SellerDashboardPage /></S>} />
            <Route path="/seller/products"     element={<S><SellerProductsPage /></S>} />
            <Route path="/seller/product/new"  element={<S><SellerProductNewPage /></S>} />
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

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
