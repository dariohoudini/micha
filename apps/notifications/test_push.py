"""
R5-A push infrastructure tests.

Coverage
────────
  TestPushTokenRegister
    - auth required (401)
    - validation: short token rejected
    - new token creates row (201)
    - same user + same token = idempotent (200, no duplicate row)
    - reactivates inactive token on re-register
    - reassigns token to a new user (device-switch scenario)
    - platform normalisation: 'iphone' → 'ios', 'unknown' → 'web'

  TestPushTokenUnregister
    - auth required
    - {token: X} deactivates that one token
    - empty body deactivates ALL tokens for the user
    - does NOT touch another user's tokens

  TestPushDispatcher
    - send_to_user with no tokens returns {skipped: 1}
    - send_to_user with PUSH_NOTIFICATIONS_ENABLED=False is no-op
    - send_to_user fans out across multiple devices
    - back-compat: legacy user.fcm_token migrates on first send
    - dead-token FCM error deactivates the row
    - send respects user.push_notifications=False
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

from apps.notifications.device_models import DeviceToken
from apps.notifications.push_service import send_to_user

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='push@test.com',
        password='TestPass123!',
        is_email_verified=True,
        status='active',
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email='other@test.com',
        password='TestPass123!',
        is_email_verified=True,
        status='active',
    )


@pytest.fixture
def auth_client(user):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    c = APIClient()
    refresh = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return c


# ─── Register endpoint ───────────────────────────────────────────────


@pytest.mark.django_db
class TestPushTokenRegister:

    URL = '/api/v1/notifications/push/register/'

    def test_auth_required(self, api_client):
        res = api_client.post(self.URL, {'token': 'a' * 64, 'platform': 'ios'}, format='json')
        assert res.status_code in (401, 403)

    def test_token_too_short_rejected(self, auth_client):
        res = auth_client.post(
            self.URL, {'token': 'abc', 'platform': 'ios'}, format='json',
        )
        assert res.status_code == 400

    def test_new_token_creates_row(self, auth_client, user):
        res = auth_client.post(
            self.URL,
            {'token': 'fcm-token-' + 'x' * 60, 'platform': 'android'},
            format='json',
        )
        assert res.status_code == 201
        assert res.data['created'] is True
        assert DeviceToken.objects.filter(user=user).count() == 1
        t = DeviceToken.objects.get(user=user)
        assert t.platform == 'android'
        assert t.is_active is True

    def test_re_register_same_token_idempotent(self, auth_client, user):
        token = 'fcm-token-' + 'y' * 60
        auth_client.post(self.URL, {'token': token, 'platform': 'android'}, format='json')
        res = auth_client.post(self.URL, {'token': token, 'platform': 'android'}, format='json')
        assert res.status_code == 200
        assert res.data['created'] is False
        assert DeviceToken.objects.filter(user=user).count() == 1

    def test_re_register_reactivates_inactive_token(self, auth_client, user):
        token = 'fcm-token-' + 'z' * 60
        DeviceToken.objects.create(
            user=user, token=token, platform='ios',
            is_active=False, deactivation_reason='logout',
        )
        res = auth_client.post(
            self.URL, {'token': token, 'platform': 'ios'}, format='json',
        )
        assert res.status_code == 200
        t = DeviceToken.objects.get(token=token)
        assert t.is_active is True
        assert t.deactivation_reason == ''

    def test_re_register_reassigns_to_new_user(
            self, auth_client, user, other_user):
        """Device-switch: a token previously owned by other_user is
        re-registered by user. The DeviceToken row's FK should flip,
        so other_user stops receiving pushes intended for user."""
        token = 'fcm-token-' + 'q' * 60
        DeviceToken.objects.create(
            user=other_user, token=token, platform='android',
        )
        res = auth_client.post(
            self.URL, {'token': token, 'platform': 'android'}, format='json',
        )
        assert res.status_code == 200
        t = DeviceToken.objects.get(token=token)
        assert t.user_id == user.pk

    def test_platform_normalisation(self, auth_client, user):
        # 'iphone' should be normalised to 'ios'.
        auth_client.post(
            self.URL,
            {'token': 'tok-' + 'a' * 60, 'platform': 'iphone'},
            format='json',
        )
        t = DeviceToken.objects.get(user=user)
        assert t.platform == 'ios'

        # Unknown platform falls back to 'web'.
        auth_client.post(
            self.URL,
            {'token': 'tok-' + 'b' * 60, 'platform': 'foo-os'},
            format='json',
        )
        t = DeviceToken.objects.filter(user=user).order_by('-created_at').first()
        assert t.platform == 'web'


# ─── Unregister endpoint ─────────────────────────────────────────────


@pytest.mark.django_db
class TestPushTokenUnregister:

    URL = '/api/v1/notifications/push/unregister/'

    def test_auth_required(self, api_client):
        res = api_client.post(self.URL, {}, format='json')
        assert res.status_code in (401, 403)

    def test_unregister_specific_token(self, auth_client, user):
        t1 = DeviceToken.objects.create(
            user=user, token='tok-1-' + 'a' * 60, platform='android')
        t2 = DeviceToken.objects.create(
            user=user, token='tok-2-' + 'b' * 60, platform='ios')

        res = auth_client.post(self.URL, {'token': t1.token}, format='json')
        assert res.status_code == 200
        assert res.data['deactivated'] == 1

        t1.refresh_from_db()
        t2.refresh_from_db()
        assert t1.is_active is False
        assert t1.deactivation_reason == 'logout'
        assert t2.is_active is True

    def test_unregister_all_for_user(self, auth_client, user):
        DeviceToken.objects.create(
            user=user, token='tok-A-' + 'a' * 60, platform='ios')
        DeviceToken.objects.create(
            user=user, token='tok-B-' + 'b' * 60, platform='android')

        res = auth_client.post(self.URL, {}, format='json')
        assert res.status_code == 200
        assert res.data['deactivated'] == 2
        assert DeviceToken.objects.filter(user=user, is_active=False).count() == 2

    def test_unregister_does_not_touch_other_users(
            self, auth_client, user, other_user):
        other_token = DeviceToken.objects.create(
            user=other_user, token='other-' + 'x' * 60, platform='ios')
        DeviceToken.objects.create(
            user=user, token='mine-' + 'm' * 60, platform='ios')

        auth_client.post(self.URL, {}, format='json')
        other_token.refresh_from_db()
        assert other_token.is_active is True


# ─── Dispatcher: send_to_user ────────────────────────────────────────


@pytest.mark.django_db
class TestPushDispatcher:

    def test_no_tokens_no_fcm_call(self, user):
        """No DeviceToken rows and no legacy fcm_token → skipped, FCM never called."""
        with patch(
                'apps.notifications.push_service._ensure_fcm',
        ) as ensure_fcm:
            ensure_fcm.return_value = MagicMock()  # FCM mock available
            res = send_to_user(user, title='hi', body='hello')
        assert res == {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 1}

    def test_disabled_via_settings(self, user, settings):
        settings.PUSH_NOTIFICATIONS_ENABLED = False
        DeviceToken.objects.create(
            user=user, token='tok-' + 'a' * 60, platform='ios')
        res = send_to_user(user, title='hi', body='hello')
        # Each token still iterated, but _ensure_fcm returns None → skipped.
        assert res['sent'] == 0
        assert res['skipped'] >= 1

    def test_multi_device_fanout(self, user):
        for i in range(3):
            DeviceToken.objects.create(
                user=user, token=f'tok-{i}-' + 'x' * 60,
                platform='android',
            )

        mock_msg = MagicMock()
        mock_msg.send.return_value = 'fake-message-id'
        # Mock Notification + Message constructors as identity, send as
        # returning a fake id.
        mock_msg.Notification = lambda **kw: kw
        mock_msg.Message = lambda **kw: kw

        with patch(
                'apps.notifications.push_service._ensure_fcm',
        ) as ensure_fcm:
            ensure_fcm.return_value = mock_msg
            res = send_to_user(user, title='Order shipped', body='Your order is on the way')

        assert res['sent'] == 3
        assert res['failed'] == 0
        # send() called once per device.
        assert mock_msg.send.call_count == 3

    def test_legacy_fcm_token_migrated_on_first_send(self, user):
        """User has fcm_token but no DeviceToken yet → first send_to_user
        call creates a DeviceToken row from the legacy field."""
        user.fcm_token = 'legacy-' + 'L' * 60
        user.save(update_fields=['fcm_token'])

        mock_msg = MagicMock()
        mock_msg.send.return_value = 'fake-id'
        mock_msg.Notification = lambda **kw: kw
        mock_msg.Message = lambda **kw: kw

        with patch(
                'apps.notifications.push_service._ensure_fcm',
        ) as ensure_fcm:
            ensure_fcm.return_value = mock_msg
            send_to_user(user, title='t', body='b')

        # Now there's a DeviceToken row for the legacy token.
        assert DeviceToken.objects.filter(
            user=user, token=user.fcm_token,
        ).exists()

    def test_dead_token_deactivates_row(self, user):
        t = DeviceToken.objects.create(
            user=user, token='dead-' + 'd' * 60, platform='android',
        )

        # Build a fake UnregisteredError class — push_service matches by
        # class name string.
        class UnregisteredError(Exception):
            pass

        mock_msg = MagicMock()
        mock_msg.send.side_effect = UnregisteredError('token uninstalled')
        mock_msg.Notification = lambda **kw: kw
        mock_msg.Message = lambda **kw: kw

        with patch(
                'apps.notifications.push_service._ensure_fcm',
        ) as ensure_fcm:
            ensure_fcm.return_value = mock_msg
            res = send_to_user(user, title='t', body='b')

        assert res['failed'] == 1
        assert res['deactivated'] == 1
        t.refresh_from_db()
        assert t.is_active is False
        assert t.deactivation_reason == 'fcm_unregistered'

    def test_push_notifications_disabled_at_user_level(self, user):
        """If user.push_notifications=False, send is skipped entirely."""
        user.push_notifications = False
        user.save(update_fields=['push_notifications'])
        DeviceToken.objects.create(
            user=user, token='tok-' + 'p' * 60, platform='ios')
        res = send_to_user(user, title='t', body='b')
        assert res == {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 1}
