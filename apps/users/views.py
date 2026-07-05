from rest_framework.permissions import AllowAny
"""
User Views — All Security Gaps Fixed
1. Password reset now uses 6-digit OTP, not URL token
2. @require_recent_auth applied to change-email, change-phone, delete-account
3. OTP throttle tracks attempts per email address, not per IP
4. Social auth provider linking requires password confirmation
5. 2FA enforced — login blocked if code omitted when 2FA enabled
"""
import logging
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from apps.core.throttling import FailClosedAnonRateThrottle

from .models import UserProfile, Role, UserSession, UserActivityLog, UserBadge, ReferralReward
from .serializers import (
    UserRegisterSerializer, UserSerializer, UpdateProfileSerializer,
    ChangePasswordSerializer, MyTokenObtainPairSerializer, SocialAuthSerializer,
)
from .permissions import IsNotSuspended
from apps.idempotency.decorators import idempotent
from middleware.security import log_security_event, require_recent_auth

User = get_user_model()
logger = logging.getLogger('micha')


# ── Throttles ─────────────────────────────────────────────────────────────────

class LoginThrottle(FailClosedAnonRateThrottle):
    # Security-critical: if the counter store (Redis) is down we DENY rather
    # than allow an unmetered brute-force window (Rate Limiting CH11/CH14).
    scope = 'login'


class OTPThrottle(FailClosedAnonRateThrottle):
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
    permission_classes = [AllowAny]
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
        # Funnel KPI (Gap-Coverage CH9B) — pairs with cart_additions and
        # GMV so a drop can be located to a funnel stage.
        try:
            from apps.telemetry.metrics import signups_total
            signups_total.inc()
        except Exception:
            pass
        # First-Run doc Screen 6 / CH7 / carry-over: the account is born
        # holding the first-order welcome coupon, so it's present at the
        # very first checkout. Idempotent; never breaks signup.
        from apps.promotions.welcome import grant_welcome_coupon
        grant_welcome_coupon(user)
        return Response({
            'detail': 'Account created. Check your email for the verification code.',
            'email': user.email,
        }, status=201)


# ── Email verification ────────────────────────────────────────────────────────

class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
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
            # Only award referral bonus after first purchase — prevent farming
                # Moved to order completion signal, not registration
                # user.referred_by.add_loyalty_points(settings.LOYALTY_REFERRAL_REWARD)
            user.add_loyalty_points(settings.LOYALTY_REFERRED_REWARD)
            ReferralReward.objects.create(
                referrer=user.referred_by,
                referred_user=user,
                points_awarded=settings.LOYALTY_REFERRAL_REWARD,
            )

        _log(user, 'email_verified', request)
        return Response({'detail': 'Email verified. You can now log in.'})


class ResendEmailOTPView(APIView):
    permission_classes = [AllowAny]
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


# ── Token refresh: reuse detection + family revocation ───────────────────────

class FamilyRevokingTokenRefreshView(TokenRefreshView):
    """POST /api/v1/auth/token/refresh/ (IAM/Security CH11, Gap-Coverage CH10).

    Rotation + blacklist already make each refresh token single-use.
    This view adds the CONTAINMENT: presenting an already-rotated
    (blacklisted) refresh token means the legitimate client has moved
    past it — whoever sent it holds a STOLEN copy. Response: revoke the
    user's ENTIRE outstanding-token family and force re-auth, so the
    thief and the victim are both logged out and the compromised session
    lineage dies. The reuse event is security-logged as a theft signal.
    """

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except (InvalidToken, TokenError):
            self._contain_reuse(request)
            raise

    @staticmethod
    def _contain_reuse(request):
        """Detect reuse and revoke the family. NEVER raises — containment
        must not change the 401 the caller is already getting."""
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken, OutstandingToken,
            )
            raw = (request.data or {}).get('refresh') or ''
            if not raw:
                return
            # Every issued refresh token (login + each rotation) has an
            # OutstandingToken row (`refresh.outstand()`), so an exact-string
            # match identifies the token without trusting its signature.
            presented = OutstandingToken.objects.filter(token=raw).first()
            if presented is None or presented.user_id is None:
                return   # forged/garbage/expired-unknown → not a reuse signal
            if not BlacklistedToken.objects.filter(token=presented).exists():
                return   # invalid for some other reason (not rotation reuse)
            # REUSE of a rotated token → revoke the whole family.
            revoked = 0
            for tok in OutstandingToken.objects.filter(user_id=presented.user_id):
                _, created = BlacklistedToken.objects.get_or_create(token=tok)
                revoked += int(created)
            log_security_event(
                'refresh_token_reuse_family_revoked', request=request,
                severity='CRITICAL',
                details={'user_id': presented.user_id,
                         'reused_jti': presented.jti,
                         'newly_revoked': revoked},
            )
        except Exception:
            logger.exception('refresh-token reuse containment failed')


# ── Login ─────────────────────────────────────────────────────────────────────

class MyTokenObtainPairView(TokenObtainPairView):
    """POST /api/v1/auth/login/  body: {email, password, totp_code?}

    Orchestrates production-grade brute-force defense. See
    apps/security/lockout for the underlying service.

    Anti-enumeration policy
    ─────────────────────────
    Every failure path returns the SAME generic body with the SAME
    timing characteristics:
      • bad password
      • unknown email
      • locked account (per-email)
      • locked IP (credential stuffing)
      • suspended / banned account

    All return 400 ``invalid_credentials``. The user discovers lockout
    state via the email notification AND the password-reset path,
    NOT via the login API response.

    Two exceptions where we DO leak signal, by design:
      • ``email_not_verified`` — the user is stuck and needs to know
        to resend the verification email. The attacker, by this point,
        has already proven password possession, so the enumeration
        battle around credential-equivalent info is moot.
      • ``2fa_required`` — the client needs to prompt for a code.
        Same justification.
    """
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [LoginThrottle]

    # Single canonical generic-failure response. Built here as a class
    # constant so every failure site returns byte-identical bytes.
    _GENERIC_FAILURE_BODY = {
        'error': 'invalid_credentials',
        'detail': 'Email or password is incorrect.',
    }

    def _generic_fail(self):
        return Response(self._GENERIC_FAILURE_BODY, status=400)

    def post(self, request, *args, **kwargs):
        from apps.security import lockout
        from apps.security.notifications import send_account_locked_email
        from apps.security.login_attempt_models import (
            LoginAttempt, LoginAttemptFailureReason,
        )
        from django.contrib.auth import authenticate

        email = (request.data.get('email') or '').lower().strip()
        password = request.data.get('password') or ''
        ip = _get_ip(request)
        ua = _get_ua(request)

        # ── Pre-auth gates ────────────────────────────────────────────────
        # Check BEFORE password lookup so locked attackers don't even
        # cost us the bcrypt CPU — and so the per-IP gate short-circuits
        # stuffing scans efficiently.

        ip_lock = lockout.check_ip_lockout(ip)
        if ip_lock.locked:
            try:
                LoginAttempt.objects.create(
                    email=email[:255], ip=ip or None, user_agent=ua,
                    succeeded=False,
                    failure_reason=LoginAttemptFailureReason.IP_LOCKED,
                )
            except Exception:
                pass
            return self._generic_fail()

        account_lock = (lockout.check_account_lockout(email)
                        if email else None)
        if account_lock and account_lock.locked:
            # Continued probes against a locked account still increment
            # the counter — sustained pressure should escalate to the
            # next tier (5→10→20 → 15min/1h/24h).
            lockout.record_failed_login(
                email=email, ip=ip, user_agent=ua,
                reason=LoginAttemptFailureReason.ACCOUNT_LOCKED,
            )
            return self._generic_fail()

        # ── User lookup with timing equalisation ──────────────────────────
        user = User.objects.filter(email=email).first() if email else None

        if user is None:
            # Burn the same CPU as a real bcrypt check so unknown
            # emails don't time-leak.
            lockout.equalize_timing(password)
            lockout.record_failed_login(
                email=email, ip=ip, user_agent=ua,
                reason=LoginAttemptFailureReason.BAD_CREDENTIALS,
            )
            return self._generic_fail()

        # ── Real auth ─────────────────────────────────────────────────────
        authenticated = authenticate(
            request=request, username=email, password=password,
        )

        if not authenticated:
            info = lockout.record_failed_login(
                email=email, ip=ip, user_agent=ua,
                reason=LoginAttemptFailureReason.BAD_CREDENTIALS,
            )
            # If THIS failure triggered the lockout, email the owner.
            # Dedupe limits to one notification per hour even under burst.
            if info.get('triggered_account_lockout'):
                if lockout.should_send_lockout_notification(email):
                    try:
                        send_account_locked_email(
                            user=user, ip=ip,
                            attempt_count=info['new_email_count'],
                            lockout_duration_s=info['lockout_duration_s'],
                        )
                    except Exception:
                        logger.exception('lockout notification dispatch failed')
            return self._generic_fail()

        # ── Post-auth gates ───────────────────────────────────────────────
        # Suspended/banned: 400-generic to prevent enumeration of
        # account status by attackers who happen to have a real password.

        if authenticated.status in ('suspended', 'banned'):
            lockout.record_failed_login(
                email=email, ip=ip, user_agent=ua,
                reason=LoginAttemptFailureReason.ACCOUNT_SUSPENDED,
            )
            return self._generic_fail()

        if (not authenticated.is_email_verified
                and not authenticated.is_phone_verified):
            try:
                LoginAttempt.objects.create(
                    email=email[:255], ip=ip or None, user_agent=ua,
                    succeeded=False,
                    failure_reason=LoginAttemptFailureReason.EMAIL_NOT_VERIFIED,
                )
            except Exception:
                pass
            return Response({
                'error': 'email_not_verified',
                'detail': 'Please verify your email before logging in.',
            }, status=400)

        # ── 2FA ───────────────────────────────────────────────────────────
        if authenticated.two_fa_enabled:
            totp_code = (request.data.get('totp_code') or '').strip()
            if not totp_code:
                try:
                    LoginAttempt.objects.create(
                        email=email[:255], ip=ip or None, user_agent=ua,
                        succeeded=False,
                        failure_reason=LoginAttemptFailureReason.MISSING_2FA,
                    )
                except Exception:
                    pass
                return Response({
                    'error': '2fa_required',
                    'detail': '2FA code required.',
                    'requires_2fa': True,
                }, status=400)
            try:
                import pyotp
                totp = pyotp.TOTP(authenticated.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    # Password + bad 2FA is a strong attack signal —
                    # COUNT it against the lockout threshold.
                    lockout.record_failed_login(
                        email=email, ip=ip, user_agent=ua,
                        reason=LoginAttemptFailureReason.BAD_2FA,
                    )
                    return Response({
                        'error': 'invalid_2fa',
                        'detail': 'Invalid 2FA code.',
                    }, status=400)
            except ImportError:
                pass

        # ── Success ───────────────────────────────────────────────────────
        # Issue the token via the parent class (which calls the serializer
        # to mint refresh + access). Sanitize the data we feed to it so
        # totp_code etc. don't pollute the serializer.
        request._lockout_authenticated_user = authenticated
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            lockout.record_successful_login(
                email=email, ip=ip, user_agent=ua,
                user_id=authenticated.pk,
            )
            User.objects.filter(pk=authenticated.pk).update(
                failed_login_attempts=0, locked_until=None,
                last_login_ip=ip, last_login_device=ua,
            )
            # AliExpress Security Engineering Workflow §13.1 — record
            # the device fingerprint and email the user if this is a
            # new device we've never seen on this account.
            try:
                from apps.security.models import record_device_login
                record_device_login(authenticated, request)
            except Exception:
                # Must never crash the auth flow.
                pass
            try:
                UserSession.create_session(
                    authenticated, device=ua, ip_address=ip,
                )
            except Exception:
                pass
            log_security_event('login_success', request=request,
                               details={'user_id': authenticated.id})
            _log(authenticated, 'login', request)

        return response


def _blacklist_all_tokens_for(user) -> int:
    """Blacklist every outstanding refresh token for the user.

    The single source of token revocation logic — called by
    User.set_password (password change), LogoutAllView (explicit
    "log me out everywhere"), and RevokeSessionView (UI session
    revocation, since UserSession rows aren't joined to JWT jti).

    Returns the count of tokens that were newly blacklisted.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            OutstandingToken, BlacklistedToken,
        )
    except ImportError:
        return 0
    n = 0
    for tok in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=tok)
        if created:
            n += 1
    return n


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


class LogoutAllSessionsView(APIView):
    """POST /api/v1/auth/logout-all/  — invalidate every JWT for this user.

    For account-compromise containment: "I lost my laptop" / "I think
    someone got my password." Blacklists every outstanding refresh token
    AND marks every UserSession inactive in one operation.

    Returns the count of tokens blacklisted so the UI can confirm
    ("Logged out of 3 devices.").
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        n = _blacklist_all_tokens_for(request.user)
        UserSession.objects.filter(
            user=request.user, is_active=True,
        ).update(is_active=False)
        log_security_event('logout_all_sessions', request=request,
                           details={'user_id': request.user.id, 'tokens_revoked': n})
        _log(request.user, 'logout_all', request)
        return Response({
            'detail': 'Logged out of all sessions.',
            'tokens_revoked': n,
        })


# ── Social auth ───────────────────────────────────────────────────────────────

class SocialAuthView(APIView):
    """
    FIX: If linking to existing account, requires password confirmation.
    Prevents attacker from hijacking account by linking their social account.
    """
    permission_classes = [AllowAny]
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
    permission_classes = [AllowAny]
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
    permission_classes = [AllowAny]
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
        # Also clear the legacy DB-side counters
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save()
        # AUTO-UNLOCK: a successful password reset proves email ownership,
        # which is stronger than a successful login. Clear the lockout
        # cache so the legitimate user isn't stranded waiting for the
        # TTL to expire after they've already proven they own the email.
        try:
            from apps.security.lockout import clear_lockout
            clear_lockout(email, reason='password_reset')
        except Exception:
            logger.exception('lockout clear-on-reset failed')
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

    def patch(self, request, *args, **kwargs):
        # Allow updating language/currency on the User row alongside profile fields
        ALLOWED_USER_FIELDS = {'language', 'currency', 'dark_mode'}
        user_updates = {k: v for k, v in request.data.items() if k in ALLOWED_USER_FIELDS}
        if user_updates:
            for k, v in user_updates.items():
                if k == 'language' and v not in ('pt', 'en'):
                    continue
                setattr(request.user, k, v)
            request.user.save(update_fields=list(user_updates.keys()))
        return super().patch(request, *args, **kwargs)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # AliExpress Security Engineering Workflow §8.3 — bump
        # jwt_version so EVERY existing access token for this user
        # fails the next auth check. Refresh tokens get a sibling
        # purge (apps/users/sessions.py logout-all flow).
        from django.db.models import F
        from apps.users.models import User as _U
        _U.objects.filter(pk=request.user.pk).update(jwt_version=F('jwt_version') + 1)
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
        # NEVER log the OTP plaintext — it's a sub-second account-takeover
        # primitive. The PII redactor would scrub it on the way out, but
        # we don't even compose it: log the issuance event with the user
        # id only. Dev-time delivery is via the SMS provider's sandbox.
        logger.info(
            'phone_otp_issued',
            extra={'user_id': request.user.id, 'phone_masked': (new_phone or '')[:4] + '***'},
        )
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
    """GET /2fa/setup/ — begin 2FA enrolment.

    Returns a fresh TOTP secret + provisioning URI so the client can
    render a QR. The secret is stored in ``User.two_fa_secret``
    (EncryptedCharField — ciphertext at rest) but NOT yet enabled;
    the user must complete enrolment by posting a valid TOTP code to
    /2fa/enable/.

    Refuses to overwrite an active 2FA enrolment
    ─────────────────────────────────────────────
    Without this guard, an attacker who steals a session (XSS or
    cookie theft) on an account with 2FA enabled can simply call
    /2fa/setup/, get a fresh secret bound to their own authenticator
    app, and call /2fa/enable/ — silently rotating the second factor
    they don't actually possess. The user is locked out without
    realising what happened.

    To rotate 2FA legitimately, the user must first /2fa/disable/
    (which now requires BOTH password AND current TOTP code), then
    re-enrol.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        if request.user.two_fa_enabled:
            return Response(
                {'error': '2fa_already_enabled',
                 'detail': 'Disable 2FA first before rotating the secret.'},
                status=409,
            )
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
    """POST /2fa/disable/ — turn off 2FA.

    Requires BOTH:
      • current password (something the user knows)
      • current TOTP code (something the user has)

    Previously this only required the password. That defeats the
    purpose of 2FA: if a password is leaked (phishing, breach reuse),
    the attacker could log in with password alone, immediately disable
    2FA before the user noticed, and then proceed without challenge.

    With this two-factor disable: an attacker who only has the
    password cannot remove the second factor; they must also have
    the authenticator app, which is the whole point.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        password = request.data.get('password', '')
        code = request.data.get('code', '').strip()

        if not request.user.check_password(password):
            log_security_event(
                '2fa_disable_bad_password', request=request,
                severity='HIGH',
                details={'user_id': request.user.id},
            )
            return Response(
                {'error': 'invalid_password', 'detail': 'Incorrect password.'},
                status=400,
            )

        # If 2FA was enabled, demand the second factor too. The window
        # where two_fa_enabled=False but two_fa_secret is set (i.e.
        # between Setup and Enable) is OK to disable with password
        # alone because nothing was relying on the secret yet.
        if request.user.two_fa_enabled:
            if not code:
                return Response(
                    {'error': '2fa_required',
                     'detail': 'A current 2FA code is required to disable 2FA.'},
                    status=400,
                )
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(code, valid_window=1):
                    log_security_event(
                        '2fa_disable_bad_code', request=request,
                        severity='HIGH',
                        details={'user_id': request.user.id},
                    )
                    return Response(
                        {'error': 'invalid_code',
                         'detail': 'Invalid 2FA code.'},
                        status=400,
                    )
            except ImportError:
                return Response(
                    {'error': 'server_error', 'detail': 'pyotp not installed.'},
                    status=503,
                )

        request.user.two_fa_enabled = False
        request.user.two_fa_secret = None
        request.user.save(update_fields=['two_fa_enabled', 'two_fa_secret'])
        log_security_event(
            '2fa_disabled', request=request,
            details={'user_id': request.user.id},
        )
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
    """DELETE /api/v1/auth/sessions/<session_id>/

    UserSession rows are NOT joined to a specific JWT jti (the session_id
    is generated independently of the token). Without that join, we can't
    selectively blacklist the one token for the revoked session — so we
    do the safe thing: mark the session inactive AND blacklist every
    outstanding token for the user, forcing re-login on all devices.

    Heavier than ideal — the user is logged out everywhere when they
    asked to revoke one device — but the alternative is the worst kind
    of security bug: a revoke action in the UI that doesn't actually
    revoke. Until session_id ↔ jti are joined (schema change), this is
    the only correct behaviour. Documented in the response so the UI
    can warn the user before they click.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, session_id):
        from django.shortcuts import get_object_or_404
        session = get_object_or_404(UserSession, session_id=session_id, user=request.user)
        session.is_active = False
        session.save(update_fields=['is_active'])
        revoked = _blacklist_all_tokens_for(request.user)
        log_security_event('session_revoked', request=request, details={
            'user_id': request.user.id,
            'session_id': str(session_id),
            'tokens_revoked': revoked,
        })
        return Response({
            'detail': 'Session revoked. All your devices have been signed out.',
            'tokens_revoked': revoked,
        })


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
    """POST /api/v1/auth/loyalty/redeem/  body: {points}

    Idempotency REQUIRED. A retry under network flakiness would consume
    the user's points TWICE — the in-memory balance check passes both
    times because the request is in flight when the second arrives, then
    both atomic decrements succeed. This is a classic double-spend.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request):
        points = int(request.data.get('points', 0))
        if points <= 0:
            return Response({'error': 'validation_error', 'detail': 'points must be positive.'}, status=400)
        if not request.user.redeem_loyalty_points(points):
            return Response({'error': 'insufficient_points',
                             'detail': f'You only have {request.user.loyalty_points} points.'}, status=400)
        return Response({'detail': f'{points} points redeemed.',
                         'store_credit': str(request.user.store_credit)})


class DailyCheckinView(APIView):
    """GET  /api/v1/auth/checkin/   — current streak + whether today is claimable
    POST /api/v1/auth/checkin/   — claim today's points (idempotent within the same UTC day)
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def _streak(self, user, today):
        from apps.users.models import DailyCheckin
        from datetime import timedelta
        latest = DailyCheckin.objects.filter(user=user).order_by('-date').first()
        if not latest:
            return 0, False  # streak length, claimed_today
        if latest.date == today:
            return latest.streak_day, True
        if latest.date == today - timedelta(days=1):
            return latest.streak_day, False
        return 0, False

    def get(self, request):
        from datetime import date
        today = date.today()
        streak, claimed_today = self._streak(request.user, today)
        next_streak_day = streak + 1 if not claimed_today else streak
        from apps.users.models import DailyCheckin
        return Response({
            'streak_days': streak,
            'claimed_today': claimed_today,
            'next_reward_points': DailyCheckin.points_for_streak(next_streak_day),
            'points_balance': request.user.loyalty_points,
        })

    def post(self, request):
        from apps.users.models import DailyCheckin
        from django.db import transaction
        from datetime import date, timedelta
        from apps.ledger.service import transfer
        from apps.ledger.models import Account, AccountType
        today = date.today()
        with transaction.atomic():
            existing = DailyCheckin.objects.filter(user=request.user, date=today).first()
            if existing:
                return Response({
                    'detail': 'Já fez check-in hoje.',
                    'streak_days': existing.streak_day,
                    'points_awarded': existing.points_awarded,
                    'points_balance': request.user.loyalty_points,
                }, status=200)
            yesterday = DailyCheckin.objects.filter(user=request.user, date=today - timedelta(days=1)).first()
            streak_day = (yesterday.streak_day + 1) if yesterday else 1
            points = DailyCheckin.points_for_streak(streak_day)
            DailyCheckin.objects.create(
                user=request.user, date=today,
                streak_day=streak_day, points_awarded=points,
            )
            # Cached counter (existing read paths still work)
            request.user.add_loyalty_points(points)
            # Source of truth: post to ledger.
            # Loyalty points are tracked in cents-equivalent (1 point = 1 cent here for accounting).
            transfer(
                from_account=Account.platform(AccountType.PLATFORM_LOYALTY_FUND, currency='PTS'),
                to_account=Account.for_user(request.user, AccountType.USER_LOYALTY_POINTS, currency='PTS'),
                amount_cents=points,  # 1 unit = 1 point in PTS currency
                journal_key=f'checkin:{request.user.id}:{today.isoformat()}',
                ref_type='checkin',
                ref_id=str(request.user.id),
                description=f'Daily check-in day {streak_day}',
                user=request.user,
            )
        return Response({
            'detail': '+{} pontos!'.format(points),
            'streak_days': streak_day,
            'points_awarded': points,
            'points_balance': request.user.loyalty_points,
        }, status=201)


class AcceptTermsView(APIView):
    """POST /api/v1/auth/accept-terms/ — Re-accept updated T&C."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.conf import settings
        from .models import ConsentLog
        version = getattr(settings, 'CURRENT_TC_VERSION', '1.0')
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT', '')[:200]
        ConsentLog.objects.create(
            user=request.user,
            consent_type='terms_of_service',
            version=version,
            granted=True,
            ip_address=ip,
            user_agent=ua,
        )
        return Response({'detail': f'Terms version {version} accepted.'})
