from django.urls import path
from .views import (
    AcceptTermsView, FamilyRevokingTokenRefreshView,
    UserRegisterView, VerifyEmailView, ResendEmailOTPView,
    MyTokenObtainPairView, LogoutView, LogoutAllSessionsView, SocialAuthView,
    ForgotPasswordView, ResetPasswordView,
    UserProfileView, UpdateProfileView, ChangePasswordView,
    ChangeEmailView, ChangePhoneView,
    DeleteAccountView, CancelDeletionView,
    Setup2FAView, Enable2FAView, Disable2FAView,
    DataExportView,
    SessionListView, RevokeSessionView,
    ReferralView, LoyaltyView, RedeemPointsView, DailyCheckinView,
)

urlpatterns = [
    # Registration & verification
    path('register/', UserRegisterView.as_view(), name='register'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('resend-email-otp/', ResendEmailOTPView.as_view(), name='resend-otp'),

    # Login / Logout
    path('login/', MyTokenObtainPairView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout-all/', LogoutAllSessionsView.as_view(), name='logout-all'),
    # Gap-Coverage CH10: refresh with reuse-detection — a replayed rotated
    # token revokes the whole token family (stolen-token containment).
    path('token/refresh/', FamilyRevokingTokenRefreshView.as_view(),
         name='token-refresh'),
    path('social/', SocialAuthView.as_view(), name='social-auth'),

    # Password (OTP-based reset — no URL tokens)
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Profile
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/update/', UpdateProfileView.as_view(), name='profile-update'),

    # Sensitive account changes (require X-Confirm-Password header)
    path('change-email/', ChangeEmailView.as_view(), name='change-email'),
    path('change-phone/', ChangePhoneView.as_view(), name='change-phone'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete-account'),
    path('cancel-deletion/', CancelDeletionView.as_view(), name='cancel-deletion'),

    # 2FA
    path('2fa/setup/', Setup2FAView.as_view(), name='2fa-setup'),
    path('2fa/enable/', Enable2FAView.as_view(), name='2fa-enable'),
    path('2fa/disable/', Disable2FAView.as_view(), name='2fa-disable'),

    # Sessions
    path('sessions/', SessionListView.as_view(), name='sessions'),
    path('sessions/<uuid:session_id>/', RevokeSessionView.as_view(), name='revoke-session'),

    # Loyalty & Referrals
    path('referral/', ReferralView.as_view(), name='referral'),
    path('loyalty/', LoyaltyView.as_view(), name='loyalty'),
    path('loyalty/redeem/', RedeemPointsView.as_view(), name='redeem-points'),
    path('checkin/', DailyCheckinView.as_view(), name='daily-checkin'),

    path('accept-terms/', AcceptTermsView.as_view(), name='accept-terms'),

    # Data export (GDPR / Lei 22/11)
    path('data-export/', DataExportView.as_view(), name='data-export'),
]
