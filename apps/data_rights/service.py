"""
apps/data_rights/service.py

Public entrypoints — create a DataSubjectRequest and kick off the
appropriate saga. Used by the user-facing views and by admins (the latter
can create requests on behalf of a user via the admin override path).
"""
from __future__ import annotations
from datetime import timedelta
from django.utils import timezone

from .models import DataSubjectRequest, RequestKind, RequestStatus


EXPORT_SLA_HOURS = 24
ERASE_SLA_DAYS   = 30  # Angola Lei 22/11 / GDPR Article 17


def request_export(user, *, source_ip: str = '', user_agent: str = '') -> DataSubjectRequest:
    return _create_and_run(
        user=user, kind=RequestKind.EXPORT,
        sla_at=timezone.now() + timedelta(hours=EXPORT_SLA_HOURS),
        saga_name='data_export',
        source_ip=source_ip, user_agent=user_agent,
    )


def request_erase(user, *, source_ip: str = '', user_agent: str = '') -> DataSubjectRequest:
    return _create_and_run(
        user=user, kind=RequestKind.ERASE,
        sla_at=timezone.now() + timedelta(days=ERASE_SLA_DAYS),
        saga_name='data_erase',
        source_ip=source_ip, user_agent=user_agent,
    )


def _create_and_run(*, user, kind, sla_at, saga_name, source_ip, user_agent):
    req = DataSubjectRequest.objects.create(
        user=user, user_email_at_request=user.email or '',
        kind=kind, status=RequestStatus.RUNNING,
        sla_deadline_at=sla_at,
        source_ip=source_ip or None,
        user_agent=user_agent[:200],
        started_at=timezone.now(),
    )
    try:
        from apps.sagas.runner import start, run
        from apps.sagas.models import SagaStatus
        s = start(
            saga_name,
            ref_type='data_request', ref_id=str(req.id),
            payload={'user_id': user.id, 'request_id': req.id},
        )
        s = run(s.id)
        # If the saga failed / needs_attention, finalise step never ran so
        # the request row is still RUNNING. Reflect the saga outcome here.
        if s is not None and s.status in (
            SagaStatus.FAILED, SagaStatus.NEEDS_ATTENTION, SagaStatus.ABANDONED,
        ):
            DataSubjectRequest.objects.filter(pk=req.pk).update(
                status=RequestStatus.FAILED,
                error=(s.error or 'saga failed')[:1000],
                completed_at=timezone.now(),
            )
    except Exception as e:
        DataSubjectRequest.objects.filter(pk=req.pk).update(
            status=RequestStatus.FAILED,
            error=f'{type(e).__name__}: {e}'[:1000],
            completed_at=timezone.now(),
        )
    req.refresh_from_db()
    return req
