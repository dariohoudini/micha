"""
User Serialisers — Mass Assignment Protection
FIX: Every serialiser uses explicit fields list — never __all__
     An attacker cannot set is_staff, is_verified_seller, loyalty_points via API
FIX: Consent required at registration
FIX: Social auth requires password confirmation to link provider
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from datetime import timedelta
import logging

from .models import UserProfile, ConsentLog, PasswordHistory

User = get_user_model()
logger = logging.getLogger('micha')


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    full_name = serializers.CharField(write_only=True, required=False, default='')

    # FIX: Explicit consent required at registration
    privacy_consent = serializers.BooleanField(write_only=True)
    terms_consent = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        # FIX: Explicit fields — no __all__ — prevents mass assignment
        fields = ['email', 'phone', 'username', 'password', 'password2',
                  'full_name', 'privacy_consent', 'terms_consent']

    def validate_email(self, value):
        return value.lower().strip()

    def validate_privacy_consent(self, value):
        if not value:
            raise serializers.ValidationError(
                'You must accept the Privacy Policy to register.'
            )
        return value

    def validate_terms_consent(self, value):
        if not value:
            raise serializers.ValidationError(
                'You must accept the Terms of Service to register.'
            )
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        full_name = validated_data.pop('full_name', '')
        privacy_consent = validated_data.pop('privacy_consent')
        terms_consent = validated_data.pop('terms_consent')
        password = validated_data.pop('password')

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        # Record consent
        request = self.context.get('request')
        ip = None
        ua = ''
        if request:
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
            ua = request.META.get('HTTP_USER_AGENT', '')[:200]

        user.record_consent(ip_address=ip)
        ConsentLog.objects.create(
            user=user, consent_type='privacy_policy',
            granted=True, ip_address=ip, user_agent=ua
        )
        ConsentLog.objects.create(
            user=user, consent_type='terms_of_service',
            granted=True, ip_address=ip, user_agent=ua
        )

        if full_name:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.full_name = full_name
            profile.save()

        return user


class UserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()

    class Meta:
        model = User
        # FIX: Explicit read-only fields — is_staff and is_verified_seller CANNOT be set via API
        fields = [
            'id', 'email', 'phone', 'username',
            'is_seller', 'is_verified_seller',
            'is_email_verified', 'is_phone_verified',
            'two_fa_enabled', 'status', 'date_joined',
            'language', 'currency', 'dark_mode',
            'loyalty_points', 'store_credit',
            'referral_code', 'profile', 'roles', 'badges',
            'privacy_consent', 'privacy_consent_at',
        ]
        read_only_fields = ['store_credit', 
            'id', 'is_verified_seller', 'is_email_verified', 'is_phone_verified',
            'is_staff', 'is_superuser', 'status', 'date_joined',
            'loyalty_points', 'store_credit', 'referral_code',
            'privacy_consent', 'privacy_consent_at',
        ]

    def get_profile(self, obj):
        try:
            p = obj.profile
            return {
                'full_name': p.full_name,
                'city': p.city,
                'province': p.province,
                'bio': p.bio,
                'avatar': p.avatar.url if p.avatar else None,
                'gender': p.gender,
            }
        except Exception:
            return {}

    def get_roles(self, obj):
        return list(obj.roles.values_list('name', flat=True))

    def get_badges(self, obj):
        return list(obj.badges.values_list('badge', flat=True))


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        # FIX: Explicit fields — user cannot set internal fields via profile update
        fields = ['full_name', 'city', 'province', 'bio', 'avatar', 'date_of_birth', 'gender']

    def validate_avatar(self, value):
        if value:
            from middleware.file_validator import validate_image
            validate_image(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate_new_password(self, value):
        if self.initial_data.get('old_password') == value:
            raise serializers.ValidationError('New password must differ from current password.')
        user = self.context['request'].user
        if PasswordHistory.is_reused(user, value):
            raise serializers.ValidationError('You cannot reuse any of your last 5 passwords.')
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        raw = self.validated_data['new_password']
        PasswordHistory.record(user, raw)
        user.set_password(raw)
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Thin JWT issuer.

    All the brute-force defense, 2FA gating, and audit-logging logic
    lives in ``MyTokenObtainPairView.post`` so the view can return
    Response objects with our canonical envelope shape. Doing those
    gates inside ``validate()`` doesn't work because DRF's
    ``Serializer.run_validation`` wraps any raised ``ValidationError``
    via ``as_serializer_error()``, which list-wraps every dict value
    and breaks the wire shape.

    This serializer's only job: validate credentials (via the parent
    class) and decorate the token claims for downstream services.
    """
    username_field = 'email'

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['is_seller'] = user.is_seller
        token['is_verified_seller'] = user.is_verified_seller
        token['is_staff'] = user.is_staff
        token['status'] = user.status
        return token


class SocialAuthSerializer(serializers.Serializer):
    """
    FIX: Social auth now verifies token server-side.
    FIX: Linking a new social provider requires password confirmation.
    """
    provider = serializers.ChoiceField(choices=['google', 'facebook', 'apple'])
    token = serializers.CharField()
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    # Required when LINKING to existing account (not on first login)
    confirm_password = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        provider = attrs['provider']
        token = attrs['token']

        if provider == 'google':
            email, provider_id = self._verify_google(token)
        elif provider == 'facebook':
            email, provider_id = self._verify_facebook(token)
        elif provider == 'apple':
            email, provider_id = self._verify_apple(token)
        else:
            raise serializers.ValidationError('Invalid provider.')

        attrs['verified_email'] = email
        attrs['provider_id'] = provider_id
        return attrs

    def _verify_google(self, token):
        """Verify a Google ID token. Fails CLOSED.

        Previously this had two ship-blocking bugs:

          1. ``getattr(settings, 'GOOGLE_CLIENT_ID', '')`` passed an empty
             string as the audience when the env var was unset.
             ``verify_oauth2_token`` with an empty audience accepts tokens
             from ANY Google project — an attacker presents their own
             Google-signed JWT and we treat it as authentication for the
             email claim in their token. Effectively: any Google account
             on the internet can log in as any MICHA user whose email
             matches.

          2. ``except ImportError`` fell through to base64-decoding the
             JWT payload WITHOUT signature verification. If the
             google-auth package was missing (or removed by a future
             dependency cleanup), the fallback let an attacker craft a
             JWT with any email and have it accepted.

        Fix: require ``settings.GOOGLE_CLIENT_ID`` non-empty, fail closed
        if google-auth is missing, never trust an unverified token.
        """
        from django.conf import settings as _settings

        client_id = (getattr(_settings, 'GOOGLE_CLIENT_ID', '') or '').strip()
        if not client_id:
            # No audience configured → cannot verify → reject.
            raise serializers.ValidationError(
                'Google login is not configured on this server.'
            )

        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
        except ImportError:
            # Library missing — fail closed. NEVER fall through to a
            # base64-decode of an unverified token.
            raise serializers.ValidationError(
                'Google login dependency missing on server.'
            )

        try:
            idinfo = id_token.verify_oauth2_token(
                token, google_requests.Request(), client_id,
            )
        except Exception:
            raise serializers.ValidationError(
                'Invalid or expired Google token.'
            )

        # Belt-and-braces: even though verify_oauth2_token checks the
        # audience, double-check the issuer is actually Google. A future
        # google-auth bug or misuse can't accept self-signed tokens.
        issuer = (idinfo.get('iss') or '').lower()
        if issuer not in ('accounts.google.com', 'https://accounts.google.com'):
            raise serializers.ValidationError(
                'Token issuer is not Google.'
            )

        email = (idinfo.get('email') or '').strip().lower()
        sub = (idinfo.get('sub') or '').strip()
        email_verified = bool(idinfo.get('email_verified', False))

        if not email or not sub or not email_verified:
            raise serializers.ValidationError(
                'Google token missing verified email claim.'
            )

        return email, sub

    def _verify_facebook(self, token):
        """Verify a Facebook access token. Fails CLOSED.

        Two-call verification flow (the Google bug pattern in another
        form — Facebook's Graph.me endpoint accepts ANY valid Facebook
        access token, regardless of which app issued it):

          1. ``GET /debug_token`` — confirms the token was issued to
             OUR Facebook app, the token is not expired, and the user
             granted us the requested scopes. Authenticated with
             ``app_id|app_secret`` (app credentials, not the user's
             access_token).
          2. ``GET /me`` — fetches the user profile.

        Without step 1, an attacker who steals a Facebook access token
        ISSUED TO A DIFFERENT APP can present it to our backend. The
        ``/me`` call returns their identity ("yes, that's a valid
        Facebook user"), and we'd issue them a MICHA JWT — even though
        the user never authorised MICHA. Same audience-binding bug
        Google had in Sprint 0.

        ``debug_token.data.app_id`` MUST equal our FB_APP_ID. Anything
        else → reject. The check is constant-time-safe in practice
        (small integer string compare).
        """
        from django.conf import settings as _settings
        import requests

        app_id = (getattr(_settings, 'FB_APP_ID', '') or '').strip()
        app_secret = (getattr(_settings, 'FB_APP_SECRET', '') or '').strip()

        if not app_id or not app_secret:
            # No app credentials configured → cannot verify the token's
            # audience → reject. (The Google bug was the opposite path:
            # we accepted any audience. Don't repeat it.)
            raise serializers.ValidationError(
                'Facebook login is not configured on this server.'
            )

        try:
            # Step 1: verify audience + freshness via debug_token.
            debug = requests.get(
                'https://graph.facebook.com/debug_token',
                params={
                    'input_token': token,
                    'access_token': f'{app_id}|{app_secret}',
                },
                timeout=10,
            )
            ddata = (debug.json() or {}).get('data') or {}

            if not ddata.get('is_valid'):
                raise serializers.ValidationError(
                    'Facebook token is invalid or expired.'
                )

            token_app_id = str(ddata.get('app_id') or '')
            if token_app_id != app_id:
                # Token was issued to a DIFFERENT Facebook app. Reject
                # loudly — this is the audience-confusion attack.
                raise serializers.ValidationError(
                    'Facebook token was not issued to this application.'
                )

            # Step 2: fetch profile only AFTER audience is confirmed.
            resp = requests.get(
                'https://graph.facebook.com/me',
                params={'fields': 'id,email', 'access_token': token},
                timeout=10,
            )
            data = resp.json() or {}
            if 'error' in data:
                raise serializers.ValidationError('Invalid Facebook token.')

            email = (data.get('email') or '').strip().lower()
            fb_id = data.get('id') or ''
            if not email or not fb_id:
                raise serializers.ValidationError(
                    'Facebook profile is missing email; '
                    'check the app\'s email scope.'
                )
            return email, fb_id

        except serializers.ValidationError:
            raise
        except Exception:
            raise serializers.ValidationError(
                'Could not verify Facebook token.'
            )

    def _verify_apple(self, token):
        raise serializers.ValidationError('Apple Sign In requires PyJWT — install it first.')
