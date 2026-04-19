"""
User Views — All Security Gaps Fixed
1. Password reset now uses 6-digit OTP, not URL token
2. @require_recent_auth applied to change-email, change-phone, delete-account
3. OTP throttle tracks attempts per email address, not per IP
4. Social auth provider linking requires password confirmation
5. 2FA enforced — login blocked if code omitted when 2FA enabled
"""
import logging
from django.contrib.auth import get_user_model, authenticate
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from .models import UserProfile, Role, UserSession, UserActivityLog, UserBadge, ReferralReward, ConsentLog
from .serializers import (
    UserRegisterSerializer, UserSerializer, UpdateProfileSerializer,
    ChangePasswordSerializer, MyTokenObtainPairSerializer, SocialAuthSerializer,
)
from .permissions import IsNotSuspended
from middleware.security import log_security_event, require_recent_auth

User = get_user_model()
logger = logging.getLogger('micha')


# ── Throttles ─────────────────────────────────────────────────────────────────

class LoginThrottle(AnonRateThrottle):
    scope = 'login'


class OTPThrottle(AnonRateThrottle):
    """
    FIX: Rate limit per email address, not per IP.
    Behind VPN/proxy all requests look like different IPs.
    Cache key includes email so limit is per account.
    """
    scope = 'otp'

    def get_cache_key(self, request, view):
        email = request.data.get('email', '').lower().strip()
        if email:
            return f'throttle_otp_{email}'
        return super().get_cache_key(request, view)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')

def _get_ua(request):
    return request.META.get('HTTP_USER_AGENT', '')[:200]

def _log(user, action, request):
    UserActivityLog.objects.create(
        user=user, action=action,
        ip_address=_get_ip(request), device=_get_ua(request),
    )


# ── Registration ──────────────────────────────────────────────────────────────

class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def create(self, request, *args, **kwargs):
        account_type = request.data.get('account_type', 'buyer')
        referral_code = request.data.get('referral_code', '').strip()

        if account_type not in ('buyer', 'seller'):
            return Response({'error': 'validation_error', 'detail': "account_type must be 'buyer' or 'seller'."}, status=400)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        if referral_code:
            try:
                referrer = User.objects.get(referral_code=referral_code)
                if referrer.pk != user.pk:
                    user.referred_by = referrer
                    user.save(update_fields=['referred_by'])
            except User.DoesNotExist:
                pass

        if account_type == 'seller':
            user.is_seller = True
            user.assign_role(Role.SELLER, assigned_by=None, ip_address=_get_ip(request))
            user.save(update_fields=['is_seller'])
        else:
            user.assign_role(Role.CONSUMER, assigned_by=None, ip_address=_get_ip(request))

        user.generate_referral_code()
        UserBadge.objects.get_or_create(user=user, badge='new_buyer')

        otp = user.generate_email_otp()
        send_mail(
            subject='Verify your MICHA account',
            message=f'Welcome to MICHA!\n\nYour verification code: {otp}\n\nExpires in 10 minutes.\nDo not share this code with anyone.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        _log(user, 'register', request)
        return Response({
            'detail': 'Account created. Check your email for the verification code.',
            'email': user.email,
        }, status=201)


# ── Email verification ────────────────────────────────────────────────────────

class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPThrottle]

    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        otp = request.data.get('otp', '').strip()
        if not email or not otp:
            return Response({'error': 'validation_error', 'detail': 'Email and OTP required.'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'invalid_otp', 'detail': 'Invalid or expired code.'}, status=400)

        if user.is_email_verified:
            return Response({'detail': 'Email already verified.'})

        if not user.verify_email_otp(otp):
            log_security_event('otp_verification_failed', request=request, severity='WARNING',
                               details={'email': email[:3] + '***'})
            return Response({'error': 'invalid_otp', 'detail': 'Invalid or expired code.'}, status=400)

        user.mark_email_verified()

        # Award referral points after verification (not on registration — prevents gaming)
        if user.referred_by:
            user.referred_by.add_loyalty_points(settings.LOYALTY_REFERRAL_REWARD)
            user.add_loyalty_points(settings.LOYALTY_REFERRED_REWARD)
            ReferralReward.objects.create(
                referrer=user.referred_by,
                referred_user=user,
                points_awarded=settings.LOYALTY_REFERRAL_REWARD,
            )

        _log(user, 'email_verified', request)
        return Response({'detail': 'Email verified. You can now log in.'})


class ResendEmailOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPThrottle]  # Per-email throttle

    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': 'If that email exists, a code has been sent.'})

        if user.is_email_verified:
            return Response({'detail': 'Email already verified.'})

        otp = user.generate_email_otp()
        send_mail(
            subject='Your new MICHA verification code',
            message=f'Your verification code: {otp}\n\nExpires in 10 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        return Response({'detail': 'If that email exists, a code has been sent.'})


# ── Login ─────────────────────────────────────────────────────────────────────

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            email = request.data.get('email', '').lower()
            try:
                user = User.objects.get(email=email)
                user.last_login_ip = _get_ip(request)
                user.last_login_device = _get_ua(request)
                user.save(update_fields=['last_login_ip', 'last_login_device'])
                UserSession.create_session(user, device=_get_ua(request), ip_address=_get_ip(request))
                log_security_event('login_success', request=request, details={'user_id': user.id})
                _log(user, 'login', request)
            except User.DoesNotExist:
                pass
        return response


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get('refresh'))
            token.blacklist()
            _log(request.user, 'logout', request)
            return Response({'detail': 'Logged out successfully.'})
        except Exception:
            return Response({'error': 'invalid_token', 'detail': 'Invalid token.'}, status=400)


# ── Social auth ───────────────────────────────────────────────────────────────

class SocialAuthView(APIView):
    """
    FIX: If linking to existing account, requires password confirmation.
    Prevents attacker from hijacking account by linking their social account.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = SocialAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['verified_email']
        provider = serializer.validated_data['provider']
        provider_id = serializer.validated_data['provider_id']
        full_name = serializer.validated_data.get('full_name', '')
        confirm_password = serializer.validated_data.get('confirm_password', '')

        if not email:
            return Response({'error': 'validation_error',
                             'detail': 'Social account has no email. Register with email instead.'}, status=400)

        existing = User.objects.filter(email=email.lower()).first()

        if existing:
            # FIX: Linking requires password confirmation
            field_map = {'google': 'google_id', 'facebook': 'facebook_id', 'apple': 'apple_id'}
            already_linked = getattr(existing, field_map[provider], None)

            if not already_linked:
                # Not yet linked — require password to confirm ownership
                if not confirm_password:
                    return Response({
                        'error': 'password_required',
                        'detail': 'An account with this email exists. Provide your password to link this social account.',
                    }, status=403)
                if not existing.check_password(confirm_password):
                    log_security_event('social_link_failed', request=request, severity='WARNING',
                                       details={'provider': provider, 'email': email[:3] + '***'})
                    return Response({'error': 'invalid_password', 'detail': 'Incorrect password.'}, status=403)

                setattr(existing, field_map[provider], provider_id[:100])
                existing.save(update_fields=[field_map[provider]])
                log_security_event('social_account_linked', request=request,
                                   details={'provider': provider, 'user_id': existing.id})

            user = existing
            created = False
        else:
            user = User.objects.create(email=email.lower(), is_email_verified=True)
            user.assign_role(Role.CONSUMER, assigned_by=None, ip_address=_get_ip(request))
            user.generate_referral_code()
            UserBadge.objects.get_or_create(user=user, badge='new_buyer')
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if full_name:
                profile.full_name = full_name
                profile.save()
            field_map = {'google': 'google_id', 'facebook': 'facebook_id', 'apple': 'apple_id'}
            setattr(user, field_map[provider], provider_id[:100])
            user.save(update_fields=[field_map[provider]])
            created = True

        refresh = RefreshToken.for_user(user)
        _log(user, f'social_login_{provider}', request)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'is_new_user': created,
            'email': user.email,
        })


# ── Password reset — FIX: OTP not URL token ───────────────────────────────────

class ForgotPasswordView(APIView):
    """
    FIX: Sends 6-digit OTP instead of URL token.
    URL tokens appear in server logs, browser history, and Referer headers.
    OTP is hashed before storage — plain value never touches the DB.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPThrottle]

    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        try:
            user = User.objects.get(email=email)
            otp = user.generate_password_reset_token()  # now returns 6-digit OTP
            send_mail(
                subject='Reset your MICHA password',
                message=(
                    f'Your password reset code: {otp}\n\n'
                    f'Expires in 1 hour.\n'
                    f'If you did not request this, ignore this email.\n'
                    f'Do not share this code with anyone.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except User.DoesNotExist:
            pass  # Never reveal if email exists
        return Response({'detail': 'If that email exists, a reset code has been sent.'})


class ResetPasswordView(APIView):
    """
    FIX: Verify 6-digit OTP, not URL token.
    POST { email, otp, new_password }
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPThrottle]

    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        otp = request.data.get('otp', '').strip()
        new_password = request.data.get('new_password', '')

        if not all([email, otp, new_password]):
            return Response({'error': 'validation_error',
                             'detail': 'email, otp, and new_password are required.'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'invalid_code', 'detail': 'Invalid or expired code.'}, status=400)

        if not user.verify_password_reset_token(otp):
            log_security_event('password_reset_failed', request=request, severity='WARNING',
                               details={'email': email[:3] + '***'})
            return Response({'error': 'invalid_code', 'detail': 'Invalid or expired code.'}, status=400)

        user.set_password(new_password)  # also blacklists all JWT tokens
        user.clear_password_reset()
        user.save()
        log_security_event('password_reset_success', request=request, details={'user_id': user.id})
        _log(user, 'password_reset', request)
        return Response({'detail': 'Password reset successfully. You can now log in.'})


# ── Profile ────────────────────────────────────────────────────────────────────

class UserProfileView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    def get_object(self): return self.request.user


class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UpdateProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_security_event('password_changed', request=request, details={'user_id': request.user.id})
        _log(request.user, 'password_changed', request)
        return Response({'detail': 'Password changed. All other sessions have been logged out.'})


class ChangeEmailView(APIView):
    """
    FIX: @require_recent_auth applied — changing email requires password confirmation.
    POST { new_email } with X-Confirm-Password header
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @require_recent_auth()
    def post(self, request):
        new_email = request.data.get('new_email', '').lower().strip()
        if not new_email:
            return Response({'error': 'validation_error', 'detail': 'new_email required.'}, status=400)
        if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
            return Response({'error': 'email_taken', 'detail': 'Email already in use.'}, status=409)
        token = request.user.generate_email_change_token(new_email)
        otp = request.user._generate_otp()
        send_mail(
            subject='Confirm your new email — MICHA',
            message=f'Confirm your new email address with this code: {otp}\n\nExpires in 1 hour.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[new_email],
            fail_silently=True,
        )
        log_security_event('email_change_requested', request=request, details={'user_id': request.user.id})
        return Response({'detail': f'Confirmation code sent to {new_email}.'})


class ChangePhoneView(APIView):
    """FIX: @require_recent_auth applied — changing phone requires password confirmation."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @require_recent_auth()
    def post(self, request):
        new_phone = request.data.get('new_phone', '').strip()
        if not new_phone:
            return Response({'error': 'validation_error', 'detail': 'new_phone required.'}, status=400)
        if User.objects.filter(phone=new_phone).exclude(pk=request.user.pk).exists():
            return Response({'error': 'phone_taken', 'detail': 'Phone number already in use.'}, status=409)
        otp = request.user.generate_phone_otp()
        # TODO: Send SMS via Africa's Talking or Twilio
        logger.info(f"Phone OTP for {new_phone}: {otp}")  # Console in dev
        return Response({'detail': f'Verification code sent to {new_phone}.'})


class DeleteAccountView(APIView):
    """FIX: @require_recent_auth applied — account deletion requires password confirmation."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @require_recent_auth()
    def post(self, request):
        reason = request.data.get('reason', '')
        request.user.deletion_requested_at = timezone.now()
        request.user.save(update_fields=['deletion_requested_at'])
        log_security_event('account_deletion_requested', request=request,
                           details={'user_id': request.user.id, 'reason': reason[:100]})
        _log(request.user, 'deletion_requested', request)
        return Response({
            'detail': 'Account deletion scheduled. Your account will be permanently deleted in 30 days.',
            'deletion_date': str((timezone.now() + timezone.timedelta(days=30)).date()),
        })


class CancelDeletionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.deletion_requested_at:
            return Response({'error': 'no_deletion_pending', 'detail': 'No pending deletion.'}, status=400)
        request.user.deletion_requested_at = None
        request.user.save(update_fields=['deletion_requested_at'])
        return Response({'detail': 'Account deletion cancelled.'})


# ── 2FA ───────────────────────────────────────────────────────────────────────

class Setup2FAView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        try:
            import pyotp
            secret = pyotp.random_base32()
            request.user.two_fa_secret = secret
            request.user.save(update_fields=['two_fa_secret'])
            totp = pyotp.TOTP(secret)
            uri = totp.provisioning_uri(name=request.user.email, issuer_name='MICHA')
            return Response({'secret': secret, 'qr_uri': uri})
        except ImportError:
            return Response({'error': 'server_error', 'detail': 'pyotp not installed.'}, status=503)


class Enable2FAView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        code = request.data.get('code', '').strip()
        try:
            import pyotp
            if not request.user.two_fa_secret:
                return Response({'error': 'validation_error', 'detail': 'Call /2fa/setup/ first.'}, status=400)
            totp = pyotp.TOTP(request.user.two_fa_secret)
            if not totp.verify(code, valid_window=1):
                return Response({'error': 'invalid_code', 'detail': 'Invalid 2FA code.'}, status=400)
            request.user.two_fa_enabled = True
            request.user.save(update_fields=['two_fa_enabled'])
            log_security_event('2fa_enabled', request=request, details={'user_id': request.user.id})
            return Response({'detail': '2FA enabled.'})
        except ImportError:
            return Response({'error': 'server_error', 'detail': 'pyotp not installed.'}, status=503)


class Disable2FAView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        password = request.data.get('password', '')
        if not request.user.check_password(password):
            return Response({'error': 'invalid_password', 'detail': 'Incorrect password.'}, status=400)
        request.user.two_fa_enabled = False
        request.user.two_fa_secret = None
        request.user.save(update_fields=['two_fa_enabled', 'two_fa_secret'])
        log_security_event('2fa_disabled', request=request, details={'user_id': request.user.id})
        return Response({'detail': '2FA disabled.'})


# ── Data Export ───────────────────────────────────────────────────────────────

class DataExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        data = {
            'account': {
                'id': user.id, 'email': user.email,
                'phone': user.phone, 'username': user.username,
                'date_joined': str(user.date_joined),
                'is_seller': user.is_seller, 'loyalty_points': user.loyalty_points,
                'store_credit': str(user.store_credit), 'referral_code': user.referral_code,
                'privacy_consent_at': str(user.privacy_consent_at) if user.privacy_consent_at else None,
            },
            'profile': {
                'full_name': profile.full_name if profile else '',
                'city': profile.city if profile else '',
                'bio': profile.bio if profile else '',
                'date_of_birth': str(profile.date_of_birth) if profile and profile.date_of_birth else '',
            } if profile else {},
            'orders': [],
            'activity_log': [],
            'consent_log': [],
        }
        try:
            from apps.orders.models import Order
            orders = Order.objects.filter(buyer=user).values('id', 'status', 'total', 'created_at')
            data['orders'] = [{'id': str(o['id']), 'status': o['status'],
                               'total': str(o['total']), 'created_at': str(o['created_at'])} for o in orders]
        except Exception:
            pass

        logs = UserActivityLog.objects.filter(user=user).order_by('-created_at')[:100]
        data['activity_log'] = [{'action': l.action, 'at': str(l.created_at)} for l in logs]

        from .models import ConsentLog
        consents = ConsentLog.objects.filter(user=user)
        data['consent_log'] = [{'type': c.consent_type, 'granted': c.granted,
                                 'version': c.version, 'at': str(c.created_at)} for c in consents]

        _log(user, 'data_export', request)
        return Response(data)


class SessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sessions = UserSession.objects.filter(user=request.user, is_active=True)
        return Response([{'id': str(s.session_id), 'device': s.device,
                          'ip': s.ip_address, 'last_activity': str(s.last_activity)} for s in sessions])


class RevokeSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, session_id):
        from django.shortcuts import get_object_or_404
        session = get_object_or_404(UserSession, session_id=session_id, user=request.user)
        session.is_active = False
        session.save(update_fields=['is_active'])
        return Response({'detail': 'Session revoked.'})


class ReferralView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            'referral_code': request.user.referral_code,
            'referral_url': f"{settings.FRONTEND_URL}/join?ref={request.user.referral_code}",
            'total_referrals': request.user.referrals.count(),
            'points_earned': ReferralReward.objects.filter(
                referrer=request.user
            ).aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('points_awarded'))['total'] or 0,
        })


class LoyaltyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            'points': request.user.loyalty_points,
            'store_credit': str(request.user.store_credit),
            'value_per_point': '0.01 AOA',
        })


class RedeemPointsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        points = int(request.data.get('points', 0))
        if points <= 0:
            return Response({'error': 'validation_error', 'detail': 'points must be positive.'}, status=400)
        if not request.user.redeem_loyalty_points(points):
            return Response({'error': 'insufficient_points',
                             'detail': f'You only have {request.user.loyalty_points} points.'}, status=400)
        return Response({'detail': f'{points} points redeemed.',
                         'store_credit': str(request.user.store_credit)})
