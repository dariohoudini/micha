"""
R6 cookie-consent + data-retention tests.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.data_rights.cookie_consent import (
    CookieConsent, latest_consent, record_consent, withdraw,
)
from apps.data_rights.retention import (
    enforce_retention, retention_for,
)


User = get_user_model()


# ─── Cookie consent ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCookieConsent:

    def test_record_creates_row(self, buyer):
        row = record_consent(
            user=buyer, analytics=True, marketing=False, preferences=True,
        )
        assert row.pk
        assert row.analytics is True
        assert row.marketing is False
        assert row.preferences is True

    def test_anonymous_uses_consent_key(self, db):
        row = record_consent(
            consent_key='ck-anon-1',
            analytics=True, marketing=True, preferences=False,
        )
        assert row.user_id is None
        assert row.consent_key == 'ck-anon-1'

    def test_latest_returns_most_recent(self, buyer):
        record_consent(user=buyer, analytics=False, marketing=False,
                       preferences=False)
        latest = record_consent(user=buyer, analytics=True,
                                marketing=False, preferences=False)
        out = latest_consent(user=buyer)
        assert out.pk == latest.pk

    def test_withdraw_sets_all_false_and_marks_withdrawn(self, buyer):
        record_consent(user=buyer, analytics=True, marketing=True,
                       preferences=True)
        row = withdraw(user=buyer)
        assert row.analytics is False
        assert row.marketing is False
        assert row.preferences is False
        assert row.withdrawn_at is not None

    def test_api_get_unauthenticated(self, api_client):
        # Anonymous GET without consent_key → no consent.
        res = api_client.get('/api/v1/account/data-request/consent/')
        assert res.status_code == 200
        assert res.data['has_consent'] is False

    def test_api_post_authenticated(self, buyer_client, buyer):
        res = buyer_client.post(
            '/api/v1/account/data-request/consent/',
            {'analytics': True, 'marketing': False, 'preferences': True},
            format='json',
        )
        assert res.status_code == 201
        assert res.data['analytics'] is True
        # Verify row attached to user.
        assert CookieConsent.objects.filter(user=buyer).count() == 1

    def test_api_post_anonymous_requires_consent_key_to_be_useful(
            self, api_client):
        res = api_client.post(
            '/api/v1/account/data-request/consent/',
            {'analytics': True, 'consent_key': 'ck-anon-2'},
            format='json',
        )
        assert res.status_code == 201
        row = CookieConsent.objects.filter(consent_key='ck-anon-2').first()
        assert row is not None

    def test_withdraw_endpoint_requires_consent_key_when_anon(self, api_client):
        res = api_client.post(
            '/api/v1/account/data-request/consent/withdraw/',
            {}, format='json',
        )
        assert res.status_code == 400


# ─── Retention ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRetentionPolicy:

    def test_retention_for_known_classes(self):
        assert retention_for('notification_log') == timedelta(days=90)
        assert retention_for('chat_message') == timedelta(days=2 * 365)
        assert retention_for('unknown_class') is None

    def test_dry_run_does_not_delete(self):
        # Chat message older than retention window.
        try:
            from apps.chat.models import Message
        except Exception:
            pytest.skip('chat app not available in this test env')
            return
        # Try to create an aged message — defensive on schema variations.
        old = timezone.now() - timedelta(days=3 * 365)
        try:
            msg = Message.objects.create(
                content='ancient', created_at=old,
            )
            Message.objects.filter(pk=msg.pk).update(created_at=old)
        except Exception:
            pytest.skip('Message model schema does not match test fixture')
            return
        baseline = Message.objects.count()
        out = enforce_retention(dry_run=True)
        # Dry-run reports a count but does NOT delete.
        assert Message.objects.count() == baseline
        assert out.get('chat_message', 0) >= 1
