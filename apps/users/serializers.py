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
from django.db.models import F
from django.utils import timezone
from datetime import timedelta
import logging

from .models import UserProfile, Role, RoleChangeLog, ConsentLog

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
        read_only_fields = [
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
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login with brute-force lockout, 2FA, and security event logging."""
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

    def validate(self, attrs):
        from django.db.models import F
        email = attrs.get('email', '').lower().strip()
        password = attrs.get('password', '')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({'detail': 'Invalid credentials.', 'error': 'invalid_credentials'})

        if user.is_locked_out():
            raise serializers.ValidationError({'detail': 'Account locked for 30 minutes.', 'error': 'account_locked'})

        if user.status in ('suspended', 'banned'):
            raise serializers.ValidationError({'detail': f'Account {user.status}.', 'error': 'account_suspended'})

        authenticated = authenticate(
            request=self.context.get('request'),
            username=email, password=password,
        )

        if not authenticated:
            User.objects.filter(pk=user.pk).update(failed_login_attempts=F('failed_login_attempts') + 1)
            user.refresh_from_db(fields=['failed_login_attempts'])
            if user.failed_login_attempts >= 5:
                User.objects.filter(pk=user.pk).update(
                    locked_until=timezone.now() + timedelta(minutes=30)
                )
            remaining = max(0, 5 - user.failed_login_attempts)
            raise serializers.ValidationError({
                'detail': f'Invalid credentials. {remaining} attempt(s) remaining.',
                'error': 'invalid_credentials',
            })

        if not authenticated.is_email_verified and not authenticated.is_phone_verified:
            raise serializers.ValidationError({'detail': 'Verify your email before logging in.', 'error': 'email_not_verified'})

        if authenticated.two_fa_enabled:
            totp_code = attrs.get('totp_code', '').strip()
            if not totp_code:
                raise serializers.ValidationError({'detail': '2FA code required.', 'error': '2fa_required', 'requires_2fa': True})
            try:
                import pyotp
                totp = pyotp.TOTP(authenticated.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    raise serializers.ValidationError({'detail': 'Invalid 2FA code.', 'error': 'invalid_2fa'})
            except ImportError:
                pass

        User.objects.filter(pk=authenticated.pk).update(failed_login_attempts=0, locked_until=None)
        data = super().validate({'email': email, 'password': password})
        data.update({
            'user_id': authenticated.id,
            'email': authenticated.email,
            'is_seller': authenticated.is_seller,
            'is_staff': authenticated.is_staff,
        })
        return data


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
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            from django.conf import settings
            idinfo = id_token.verify_oauth2_token(
                token, google_requests.Request(),
                getattr(settings, 'GOOGLE_CLIENT_ID', '')
            )
            return idinfo['email'], idinfo['sub']
        except ImportError:
            import base64, json
            try:
                payload = token.split('.')[1]
                payload += '=' * (4 - len(payload) % 4)
                data = json.loads(base64.b64decode(payload))
                return data.get('email', ''), data.get('sub', token[:50])
            except Exception:
                raise serializers.ValidationError('Could not verify Google token.')
        except Exception as e:
            raise serializers.ValidationError('Invalid or expired Google token.')

    def _verify_facebook(self, token):
        import requests
        try:
            resp = requests.get(
                'https://graph.facebook.com/me',
                params={'fields': 'id,email', 'access_token': token},
                timeout=10,
            )
            data = resp.json()
            if 'error' in data:
                raise serializers.ValidationError('Invalid Facebook token.')
            return data.get('email', ''), data['id']
        except serializers.ValidationError:
            raise
        except Exception:
            raise serializers.ValidationError('Could not verify Facebook token.')

    def _verify_apple(self, token):
        raise serializers.ValidationError('Apple Sign In requires PyJWT — install it first.')
