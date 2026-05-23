"""
R4 moderator-queue + escalation tests.

Coverage
────────
  TestModerationQueue
    - admin auth required
    - default queue hides resolved
    - filters (status, severity, target_type, target_user_id)
    - pagination + page_size cap
    - target_snippet returned for product flags

  TestModerationDecisions
    - approve transitions pending → approved, writes audit row
    - reject  transitions pending → rejected, writes audit row,
              counts as infraction, does NOT escalate below threshold
    - escalate transitions pending → escalated, does NOT count
    - terminal-state flag returns 409 on re-decision
    - non-admin user is refused

  TestEscalation
    - below suspend threshold → no action
    - at suspend threshold → user.status='suspended', audit row
    - at ban threshold → user.status='banned', is_active=False
    - rolling window: rejections outside window don't count
    - idempotent: already-suspended user not re-suspended
    - already-banned user is no-op
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.moderation.escalation import evaluate_user
from apps.moderation.models import ContentFlag


User = get_user_model()


# ─── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin@test.com',
        password='TestPass123!',
        is_email_verified=True,
        status='active',
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def admin_client(admin):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    c = APIClient()
    refresh = RefreshToken.for_user(admin)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return c


@pytest.fixture
def offender(db):
    """A regular user whose content will get flagged."""
    return User.objects.create_user(
        email='offender@test.com',
        password='TestPass123!',
        is_email_verified=True,
        is_seller=True,
        status='active',
    )


def _flag(target_user=None, *, target_type='product', target_id=1,
          severity='medium', status='pending', auto_flagged=True,
          reason='auto-flagged keywords: scam'):
    return ContentFlag.objects.create(
        target_type=target_type,
        target_id=target_id,
        target_user=target_user,
        severity=severity,
        status=status,
        auto_flagged=auto_flagged,
        reason=reason,
    )


# ─── Queue tests ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestModerationQueue:

    def test_queue_requires_admin(self, api_client, buyer):
        # Unauthenticated → 401
        res = api_client.get('/api/v1/moderation/queue/')
        assert res.status_code in (401, 403)

        # Authenticated non-admin → 403
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        c = APIClient()
        refresh = RefreshToken.for_user(buyer)
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        res = c.get('/api/v1/moderation/queue/')
        assert res.status_code == 403

    def test_queue_default_hides_resolved(self, admin_client, offender):
        _flag(offender, status='pending', target_id=1)
        _flag(offender, status='approved', target_id=2)
        _flag(offender, status='rejected', target_id=3)
        _flag(offender, status='escalated', target_id=4)

        res = admin_client.get('/api/v1/moderation/queue/')
        assert res.status_code == 200
        # Default shows pending + escalated only.
        statuses = {r['status'] for r in res.data['results']}
        assert statuses == {'pending', 'escalated'}

    def test_queue_filter_by_status(self, admin_client, offender):
        _flag(offender, status='pending', target_id=10)
        _flag(offender, status='approved', target_id=11)

        res = admin_client.get('/api/v1/moderation/queue/?status=approved')
        assert res.status_code == 200
        assert len(res.data['results']) == 1
        assert res.data['results'][0]['status'] == 'approved'

    def test_queue_filter_by_target_type_and_severity(self, admin_client, offender):
        _flag(offender, target_type='product', severity='low', target_id=20)
        _flag(offender, target_type='review', severity='high', target_id=21)
        _flag(offender, target_type='product', severity='high', target_id=22)

        res = admin_client.get(
            '/api/v1/moderation/queue/?target_type=product&severity=high'
        )
        assert res.status_code == 200
        assert len(res.data['results']) == 1
        assert res.data['results'][0]['target_id'] == 22

    def test_queue_filter_by_target_user(self, admin_client, offender, buyer):
        _flag(offender, target_id=30)
        _flag(buyer, target_id=31)
        res = admin_client.get(
            f'/api/v1/moderation/queue/?target_user_id={offender.pk}'
        )
        assert res.status_code == 200
        assert len(res.data['results']) == 1
        assert res.data['results'][0]['target_user_email'] == 'offender@test.com'

    def test_queue_pagination_caps_page_size(self, admin_client, offender):
        for i in range(30):
            _flag(offender, target_id=100 + i)
        # Page size should default to 25.
        res = admin_client.get('/api/v1/moderation/queue/')
        assert res.status_code == 200
        assert len(res.data['results']) == 25
        assert res.data['count'] == 30

    def test_queue_target_snippet_for_product(self, admin_client, offender, product):
        _flag(offender, target_type='product', target_id=product.pk)
        res = admin_client.get('/api/v1/moderation/queue/')
        assert res.status_code == 200
        snippet = res.data['results'][0]['target_snippet']
        # Product fixture title is 'Samsung Galaxy S24'.
        assert 'Samsung' in snippet


# ─── Decision tests ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestModerationDecisions:

    def test_approve_transitions_to_approved_and_writes_audit(
            self, admin_client, admin, offender):
        from apps.admin_actions.models import AdminActionLog

        f = _flag(offender, target_id=200)
        res = admin_client.post(
            f'/api/v1/moderation/queue/{f.pk}/approve/',
            {'note': 'False positive, content is fine.'},
            format='json',
        )
        assert res.status_code == 200
        f.refresh_from_db()
        assert f.status == 'approved'
        assert f.resolved_by == admin
        assert f.resolved_at is not None
        assert f.resolution_note == 'False positive, content is fine.'

        # Audit row.
        log = AdminActionLog.objects.filter(
            action='moderate_approve',
            admin=admin,
        ).first()
        assert log is not None
        assert log.metadata['previous_status'] == 'pending'
        assert log.metadata['new_status'] == 'approved'

    def test_reject_counts_infraction_and_writes_audit(
            self, admin_client, admin, offender):
        from apps.admin_actions.models import AdminActionLog

        f = _flag(offender, target_id=201)
        res = admin_client.post(
            f'/api/v1/moderation/queue/{f.pk}/reject/',
            {'note': 'Counterfeit listing.'},
            format='json',
        )
        assert res.status_code == 200
        f.refresh_from_db()
        assert f.status == 'rejected'

        # Escalation block present.
        assert 'escalation' in res.data
        # Below suspend threshold (1 < 3) — no action.
        assert res.data['escalation']['action'] == 'none'
        assert res.data['escalation']['infractions'] == 1

        # Audit row.
        log = AdminActionLog.objects.filter(
            action='moderate_reject', admin=admin,
        ).first()
        assert log is not None

    def test_escalate_transitions_and_no_infraction(
            self, admin_client, admin, offender):
        f = _flag(offender, target_id=202)
        res = admin_client.post(
            f'/api/v1/moderation/queue/{f.pk}/escalate/',
            {'note': 'Needs senior review.'},
            format='json',
        )
        assert res.status_code == 200
        f.refresh_from_db()
        assert f.status == 'escalated'
        # escalate does NOT include escalation block (no infraction).
        assert 'escalation' not in res.data

    def test_terminal_state_flag_rejects_re_decision(
            self, admin_client, offender):
        f = _flag(offender, status='approved', target_id=203)
        res = admin_client.post(
            f'/api/v1/moderation/queue/{f.pk}/reject/',
            {'note': 'changed mind'},
            format='json',
        )
        assert res.status_code == 409
        # Body is normalised to {error, detail, request_id} by the
        # error-envelope middleware. Status string is embedded in detail.
        assert 'approved' in res.data['detail']
        # Flag stays in approved — not overwritten by the rejected request.
        f.refresh_from_db()
        assert f.status == 'approved'

    def test_non_admin_cannot_decide(self, api_client, buyer, offender):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        c = APIClient()
        refresh = RefreshToken.for_user(buyer)
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        f = _flag(offender, target_id=204)
        res = c.post(
            f'/api/v1/moderation/queue/{f.pk}/approve/',
            {'note': 'nope'},
            format='json',
        )
        assert res.status_code == 403


# ─── Escalation engine tests ─────────────────────────────────────────


@pytest.mark.django_db
class TestEscalation:

    def _reject_n(self, offender, n: int):
        """Create n already-rejected flags against offender, resolved
        within the rolling window. Used to set up escalation thresholds
        without going through the view layer."""
        now = timezone.now()
        for i in range(n):
            ContentFlag.objects.create(
                target_type='product',
                target_id=1000 + i,
                target_user=offender,
                reason='test infraction',
                auto_flagged=True,
                status='rejected',
                resolved_at=now,
            )

    def test_below_suspend_threshold_no_action(self, offender, settings):
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5
        self._reject_n(offender, 2)
        result = evaluate_user(offender)
        assert result.action == 'none'
        offender.refresh_from_db()
        assert offender.status == 'active'

    def test_at_suspend_threshold_user_suspended(self, offender, settings):
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5
        self._reject_n(offender, 3)
        result = evaluate_user(offender)
        assert result.action == 'suspend'
        assert result.infractions == 3
        offender.refresh_from_db()
        assert offender.status == 'suspended'

    def test_at_ban_threshold_user_banned(self, offender, settings):
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5
        self._reject_n(offender, 5)
        result = evaluate_user(offender)
        assert result.action == 'ban'
        offender.refresh_from_db()
        assert offender.status == 'banned'
        assert offender.is_active is False

    def test_rejections_outside_window_dont_count(self, offender, settings):
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5
        settings.MODERATION_INFRACTION_WINDOW_DAYS = 30

        # 5 old rejections, 1 recent. Should NOT escalate.
        old = timezone.now() - timedelta(days=60)
        for i in range(5):
            ContentFlag.objects.create(
                target_type='product', target_id=2000 + i,
                target_user=offender, reason='old',
                status='rejected', resolved_at=old, auto_flagged=True,
            )
        ContentFlag.objects.create(
            target_type='product', target_id=2999,
            target_user=offender, reason='new',
            status='rejected', resolved_at=timezone.now(), auto_flagged=True,
        )

        result = evaluate_user(offender)
        assert result.infractions == 1
        assert result.action == 'none'

    def test_already_banned_is_noop(self, offender, settings):
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5
        offender.status = 'banned'
        offender.is_active = False
        offender.save(update_fields=['status', 'is_active'])
        self._reject_n(offender, 10)
        result = evaluate_user(offender)
        assert result.action == 'already_banned'

    def test_already_suspended_user_not_re_suspended(self, offender, settings):
        """Idempotent: hitting the threshold a second time while
        already suspended should not write another suspend audit row."""
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5
        offender.status = 'suspended'
        offender.save(update_fields=['status'])
        self._reject_n(offender, 3)  # exactly at suspend, not at ban
        result = evaluate_user(offender)
        assert result.action == 'already_suspended'
        offender.refresh_from_db()
        assert offender.status == 'suspended'

    def test_disabled_via_settings(self, offender, settings):
        settings.MODERATION_ESCALATION_ENABLED = False
        self._reject_n(offender, 10)
        result = evaluate_user(offender)
        assert result.action == 'disabled'
        offender.refresh_from_db()
        assert offender.status == 'active'

    def test_end_to_end_reject_triggers_suspend(
            self, admin_client, offender, settings):
        """Integration: three rejections via the API path should
        suspend the user on the third. Verifies the view → engine
        wiring, not just the engine in isolation."""
        settings.MODERATION_SUSPEND_THRESHOLD = 3
        settings.MODERATION_BAN_THRESHOLD = 5

        for i in range(3):
            f = _flag(offender, target_id=3000 + i)
            res = admin_client.post(
                f'/api/v1/moderation/queue/{f.pk}/reject/',
                {'note': f'infraction {i + 1}'},
                format='json',
            )
            assert res.status_code == 200

        # Third reject should have triggered suspend.
        offender.refresh_from_db()
        assert offender.status == 'suspended'
        assert res.data['escalation']['action'] == 'suspend'
        assert res.data['escalation']['infractions'] == 3
