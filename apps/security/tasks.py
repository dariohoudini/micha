"""Beat tasks for security/audit hygiene."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.task_locks import singleton_task


log = logging.getLogger(__name__)


@shared_task(name='security.purge_old_login_attempts')
@singleton_task('beat:security.purge_old_login_attempts')
def purge_old_login_attempts():
    """Delete LoginAttempt rows older than the retention window.

    Two reasons for an aggressive retention default:
      • Privacy: under GDPR / Angola's Lei 22/11 we must justify
        retention of personal data (IP, UA) by purpose. After 90 days
        the forensic value is near-zero; the privacy cost stays.
      • DB size: a busy marketplace under credential-stuffing attack
        can write tens of thousands of rows per hour. Without aggressive
        purging the table balloons.

    The retention window is settings.LOGIN_ATTEMPT_RETENTION_DAYS
    (default 90). Lower it for environments with stricter retention
    policy, raise it for environments with active investigations.
    """
    from .login_attempt_models import LoginAttempt
    days = int(getattr(settings, 'LOGIN_ATTEMPT_RETENTION_DAYS', 90))
    cutoff = timezone.now() - timedelta(days=days)
    # Chunked delete to avoid one giant transaction. .delete() in Django
    # loads PKs first then issues DELETE — for million-row tables this
    # is fine in chunks.
    deleted_total = 0
    while True:
        ids = list(
            LoginAttempt.objects.filter(created_at__lt=cutoff)
            .values_list('pk', flat=True)[:5000]
        )
        if not ids:
            break
        deleted, _ = LoginAttempt.objects.filter(pk__in=ids).delete()
        deleted_total += deleted
        if len(ids) < 5000:
            break
    log.info('security.purge_old_login_attempts: deleted=%s cutoff=%s',
             deleted_total, cutoff.isoformat())
    return {'deleted': deleted_total, 'cutoff': cutoff.isoformat()}
