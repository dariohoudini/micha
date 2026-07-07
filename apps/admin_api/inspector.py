"""
The User Inspector Panel — Admin User Management doc CH8-12, CH17, CH20.1.

Opening one user assembles the complete account truth in ONE authorized,
AUDITED read: identity + lifecycle + verification ladder, security
metadata (factors — NEVER secrets), the last sign-ons (when/how/where),
the live sessions (with duration + a terminate action), the devices seen
(with multi-account fan-out — the strongest identity signal under
Angola's CGNAT, where raw IPs are shared), an explainable risk summary,
the access picture (capabilities + WHY each gate is open or closed), and
the interleaved non-repudiation timeline (what the user did + what
operators did to them).

Every endpoint here is IsAdminUser-gated and decorated with
@audit_admin_action — including the READ: opening a user is itself a
purpose-bound, recorded PII access (the watchers are watched).
"""
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from apps.admin_actions.decorators import audit_admin_action


def _lookup_user(user_id):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(id=user_id).first()


def force_reauth(user) -> dict:
    """Terminate everything NOW (doc CH5: suspend/terminate means
    'logged out now', not 'cannot log in again'):
      • deactivate all UserSession rows (the session registry)
      • blacklist every outstanding refresh token (the JWT family dies;
        access tokens age out within their short TTL)
    Returns counts for the audit trail / response."""
    from apps.users.models import UserSession
    sessions = UserSession.objects.filter(user=user, is_active=True)
    session_count = sessions.update(is_active=False)

    revoked = 0
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken, OutstandingToken,
        )
        for tok in OutstandingToken.objects.filter(user=user):
            _, created = BlacklistedToken.objects.get_or_create(token=tok)
            revoked += int(created)
    except Exception:
        pass
    return {'sessions_terminated': session_count, 'tokens_revoked': revoked}


class AdminUserInspectorView(APIView):
    """GET /api/v1/admin-api/users/<id>/inspector/ — the panel."""
    permission_classes = [IsAdminUser]

    @audit_admin_action('user.inspector_viewed', target_kwarg='user_id',
                        target_lookup=_lookup_user)
    def get(self, request, user_id):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Não encontrado'}, status=404)

        return Response({
            'identity': self._identity(user),
            'verification_ladder': self._ladder(user),
            'security': self._security(user),
            'last_sign_ons': self._sign_ons(user),
            'sessions': self._sessions(user),
            'devices': self._devices(user),
            'risk': self._risk(user),
            'access': self._access(user),
            'history': self._history(user),
        })

    # ── sections ─────────────────────────────────────────────────────

    @staticmethod
    def _lifecycle(user) -> str:
        # Derived from the existing flags (no schema change): the doc's
        # states mapped onto what the platform enforces today.
        if not user.is_active:
            return 'suspended'
        if not (user.is_phone_verified or getattr(user, 'is_email_verified', False)):
            return 'provisioned'
        return 'active'

    def _identity(self, user):
        return {
            'id': user.id,
            'email': user.email,
            'phone': getattr(user, 'phone', '') or '',
            'full_name': getattr(user, 'full_name', '') or '',
            'lifecycle': self._lifecycle(user),
            'kyc_status': self._kyc_status(user),
            'roles': {
                'buyer': True,
                'seller': user.is_seller,
                'verified_seller': user.is_verified_seller,
                'staff': user.is_staff,
            },
            'created_at': user.date_joined,
            'last_login': user.last_login,
        }

    @staticmethod
    def _kyc_status(user):
        try:
            return user.verification.status
        except Exception:
            return 'unverified'

    def _ladder(self, user):
        contact = bool(user.is_phone_verified
                       or getattr(user, 'is_email_verified', False))
        mfa = bool(user.two_fa_enabled)
        kyc = self._kyc_status(user) == 'approved'
        level = 0
        if contact:
            level = 1
        if contact and mfa:
            level = 2
        if kyc:
            level = 3
        return {'level': level, 'contact_verified': contact,
                'mfa_enrolled': mfa, 'kyc_verified': kyc}

    @staticmethod
    def _security(user):
        # Metadata ONLY — the operator never sees a secret (doc CH6).
        factors = [{'type': 'password', 'status': 'set'
                    if user.has_usable_password() else 'unusable'}]
        if user.two_fa_enabled:
            factors.append({'type': 'totp', 'status': 'enrolled'})
        if user.is_phone_verified:
            factors.append({'type': 'phone_otp', 'status': 'verified'})
        return {
            'factors': factors,
            'two_fa_enabled': user.two_fa_enabled,
            'last_login_ip': getattr(user, 'last_login_ip', None),
            'last_login_device': getattr(user, 'last_login_device', '') or '',
        }

    @staticmethod
    def _sign_ons(user):
        from apps.users.models import UserActivityLog
        rows = (UserActivityLog.objects
                .filter(user=user, action='login')
                .order_by('-created_at')[:10])
        return [{'at': r.created_at, 'ip': r.ip_address,
                 'device': r.device} for r in rows]

    @staticmethod
    def _sessions(user):
        from apps.users.models import UserSession
        now = timezone.now()
        out = []
        for s in UserSession.objects.filter(user=user, is_active=True)[:20]:
            out.append({
                'session_id': str(s.session_id),
                'started_at': s.created_at,
                'last_activity': s.last_activity,
                'duration_seconds': int((now - s.created_at).total_seconds()),
                'idle_seconds': int((now - s.last_activity).total_seconds()),
                'ip': s.ip_address,
                'device': s.device or '',
            })
        return out

    @staticmethod
    def _devices(user):
        # Device > IP under CGNAT (doc CH9). shared_with_users is the
        # multi-account fan-out — the fraud signal an operator needs.
        try:
            from apps.fraud_engine.models import DeviceUserLink
        except Exception:
            return []
        out = []
        links = (DeviceUserLink.objects.filter(user=user)
                 .select_related('device').order_by('-last_seen_at')[:10])
        for link in links:
            d = link.device
            out.append({
                'fingerprint': d.fingerprint_hash[:16],
                'platform': d.platform,
                'first_seen': link.first_seen_at,
                'last_seen': link.last_seen_at,
                'shared_with_users': d.user_links.exclude(user=user).count(),
            })
        return out

    def _risk(self, user):
        # Explainable, not a black box (doc CH10): list the factors.
        factors = []
        if not user.two_fa_enabled:
            factors.append('sem 2FA')
        if self._kyc_status(user) != 'approved' and user.is_seller:
            factors.append('vendedor sem KYC aprovado')
        try:
            from apps.fraud_engine.models import DeviceUserLink
            fan_out = 0
            for link in DeviceUserLink.objects.filter(user=user).select_related('device'):
                fan_out = max(fan_out,
                              link.device.user_links.exclude(user=user).count())
            if fan_out >= 2:
                factors.append(f'dispositivo partilhado com {fan_out} outras contas')
        except Exception:
            pass
        trust = None
        try:
            trust = float(user.trust_score.score)
        except Exception:
            pass
        badge = 'low'
        if len(factors) >= 2:
            badge = 'elevated'
        if any('partilhado' in f for f in factors):
            badge = 'high'
        return {'badge': badge, 'factors': factors, 'trust_score': trust}

    def _access(self, user):
        # "What can this user do + WHY" (doc CH13) — each gate explained.
        kyc_ok = self._kyc_status(user) == 'approved'
        active = user.is_active
        # CH5 graduated restrictions reduce capability without a suspend.
        r = getattr(user, 'restriction', None)
        restr = {'selling': False, 'withdrawal': False, 'messaging': False,
                 'reason': ''}
        if r and r.is_active:
            restr = {'selling': r.no_selling, 'withdrawal': r.no_withdrawal,
                     'messaging': r.no_messaging, 'reason': r.reason}

        def gate(enabled, why_not=''):
            return {'enabled': bool(enabled),
                    'reason': '' if enabled else why_not}

        return {
            'restriction': restr,
            'can_purchase': gate(active and not user.is_staff,
                                 'conta suspensa' if not active
                                 else 'staff não compra'),
            'can_sell': gate(active and user.is_seller and user.is_verified_seller
                             and not restr['selling'],
                             'conta suspensa' if not active
                             else 'restrito por admin' if restr['selling']
                             else 'não é vendedor' if not user.is_seller
                             else 'verificação de vendedor pendente'),
            'can_withdraw': gate(active and kyc_ok and not restr['withdrawal'],
                                 'conta suspensa' if not active
                                 else 'restrito por admin' if restr['withdrawal']
                                 else 'KYC não aprovado'),
            'can_message': gate(active and not restr['messaging'],
                                'conta suspensa' if not active
                                else 'restrito por admin' if restr['messaging']
                                else ''),
        }

    @staticmethod
    def _history(user):
        # The interleaved non-repudiation timeline (doc CH12): what the
        # user did + what operators did to them, chronological.
        from apps.users.models import UserActivityLog
        from apps.admin_actions.models import AdminActionLog
        events = [
            {'at': r.created_at, 'actor': 'user', 'action': r.action,
             'ip': r.ip_address, 'detail': r.device or ''}
            for r in UserActivityLog.objects.filter(user=user)
            .order_by('-created_at')[:30]
        ] + [
            {'at': r.created_at, 'actor': f'admin:{r.admin.email if r.admin else "?"}',
             'action': r.action, 'ip': r.ip_address,
             'detail': r.note or ''}
            for r in AdminActionLog.objects.filter(
                target_type='user', target_id=str(user.id))
            .select_related('admin').order_by('-created_at')[:30]
        ]
        events.sort(key=lambda e: e['at'], reverse=True)
        return events[:40]


class AdminUserTerminateSessionsView(APIView):
    """POST /api/v1/admin-api/users/<id>/sessions/terminate/ — force
    re-auth NOW (the account-takeover response, doc CH6/CH8)."""
    permission_classes = [IsAdminUser]

    @audit_admin_action('user.sessions_terminated', target_kwarg='user_id',
                        target_lookup=_lookup_user)
    def post(self, request, user_id):
        user = _lookup_user(user_id)
        if user is None:
            return Response({'error': 'Não encontrado'}, status=404)
        result = force_reauth(user)
        return Response({'status': 'terminated', **result})


class AdminUserImpersonateView(APIView):
    """POST /api/v1/admin-api/users/<id>/impersonate/ — view-as.

    Mints a time-boxed token to act AS the user, recorded on BOTH sides
    (the audit row attributes it to the real operator). Dangerous
    actions stay blocked even with this token (see users.stepup /
    users.impersonation). Staff/superusers cannot be impersonated."""
    permission_classes = [IsAdminUser]

    @audit_admin_action('user.impersonated', target_kwarg='user_id',
                        target_lookup=_lookup_user)
    def post(self, request, user_id):
        from apps.users.impersonation import (
            IMPERSONATION_MINUTES, issue_impersonation_token)
        target = _lookup_user(user_id)
        if target is None:
            return Response({'error': 'Não encontrado'}, status=404)
        # Never impersonate another operator (privilege-escalation guard).
        if target.is_staff or target.is_superuser:
            return Response({'error': 'cannot_impersonate_staff',
                             'detail': 'Não é possível personificar outro operador.'},
                            status=403)
        token = issue_impersonation_token(target, request.user)
        # Recorded on the target's own timeline too (the watched user
        # can see "an operator viewed as me").
        try:
            from apps.users.models import UserActivityLog
            UserActivityLog.objects.create(
                user=target, action='impersonation_started',
                device=f'by {request.user.email}')
        except Exception:
            pass
        return Response({
            'access': token,
            'expires_in_minutes': IMPERSONATION_MINUTES,
            'acting_as': {'id': target.id, 'email': target.email},
        })


class AdminUserPasswordResetView(APIView):
    """POST /api/v1/admin-api/users/<id>/password-reset/ — trigger the
    SECURE, USER-COMPLETED reset flow (doc CH6). The operator never sets
    or sees the new password — the OTP goes only to the user's email."""
    permission_classes = [IsAdminUser]

    @audit_admin_action('user.password_reset_triggered',
                        target_kwarg='user_id', target_lookup=_lookup_user)
    def post(self, request, user_id):
        from django.conf import settings
        from django.core.mail import send_mail
        user = _lookup_user(user_id)
        if user is None:
            return Response({'error': 'Não encontrado'}, status=404)
        otp = user.generate_password_reset_token()
        send_mail(
            subject='Reset your MICHA password',
            message=(f'Your password reset code: {otp}\n\n'
                     f'Expires in 1 hour.\n'
                     f'If you did not request this, ignore this email.\n'
                     f'Do not share this code with anyone.'),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        return Response({'status': 'reset_email_sent',
                         'detail': 'Código enviado para o email do utilizador.'})
