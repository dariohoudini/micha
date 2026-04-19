"""
apps/verification_gate/tasks.py

Celery tasks for verification gate.
Daily check runs at 08:00 WAT every day.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='verification_gate.daily_verification_check', queue='ai_medium')
def daily_verification_check():
    """
    Runs every day at 08:00 WAT.
    1. Locks accounts with expired BI
    2. Locks accounts with overdue monthly selfie
    3. Sends 14-day and 7-day alerts for BI expiry and selfie due
    """
    from .models import SellerVerification

    today = timezone.now().date()
    alert_14 = today + timedelta(days=14)
    alert_7 = today + timedelta(days=7)

    active = SellerVerification.objects.filter(is_active=True)

    locked_count = 0
    alerted_count = 0

    for v in active:
        # ── BI expiry checks ──────────────────────────────────────────────────
        if v.bi_expiry_date:

            # Lock if expired today
            if v.bi_expiry_date <= today:
                v.lock('bi_expired')
                notify_account_locked.delay(str(v.seller.id), 'bi_expired')
                locked_count += 1
                continue

            # 14-day alert
            if v.bi_expiry_date <= alert_14 and not v.bi_expiry_alert_14_sent:
                send_bi_expiry_alert.delay(str(v.seller.id), days=14)
                v.bi_expiry_alert_14_sent = True
                v.save(update_fields=['bi_expiry_alert_14_sent'])
                alerted_count += 1

            # 7-day alert
            elif v.bi_expiry_date <= alert_7 and not v.bi_expiry_alert_7_sent:
                send_bi_expiry_alert.delay(str(v.seller.id), days=7)
                v.bi_expiry_alert_7_sent = True
                v.save(update_fields=['bi_expiry_alert_7_sent'])
                alerted_count += 1

        # ── Monthly selfie checks ─────────────────────────────────────────────
        if v.next_selfie_due:

            # Lock if overdue
            if v.next_selfie_due < today:
                v.lock('selfie_overdue')
                notify_account_locked.delay(str(v.seller.id), 'selfie_overdue')
                locked_count += 1
                continue

            # 14-day selfie alert
            if v.next_selfie_due <= alert_14 and not v.selfie_alert_14_sent:
                send_selfie_due_alert.delay(str(v.seller.id), days=14)
                v.selfie_alert_14_sent = True
                v.save(update_fields=['selfie_alert_14_sent'])
                alerted_count += 1

            # 7-day selfie alert
            elif v.next_selfie_due <= alert_7 and not v.selfie_alert_7_sent:
                send_selfie_due_alert.delay(str(v.seller.id), days=7)
                v.selfie_alert_7_sent = True
                v.save(update_fields=['selfie_alert_7_sent'])
                alerted_count += 1

    logger.info(
        f"Daily verification check: {locked_count} accounts locked, "
        f"{alerted_count} alerts sent"
    )


@shared_task(name='verification_gate.notify_admin_new_submission', queue='ai_fast')
def notify_admin_new_submission(verification_id: str):
    """Notifies admins when a new verification is submitted."""
    from django.contrib.auth import get_user_model
    from .models import SellerVerification

    try:
        v = SellerVerification.objects.get(id=verification_id)
        User = get_user_model()
        admins = User.objects.filter(is_staff=True, is_active=True)

        for admin in admins:
            _send_notification(
                user_id=str(admin.id),
                title="Nova verificação para rever",
                body=f"{v.full_name or v.seller.email} submeteu documentos de verificação.",
                data={
                    'type': 'verification_submission',
                    'verification_id': verification_id,
                    'url': f'/admin/verification/{verification_id}/',
                }
            )
    except Exception as e:
        logger.error(f"notify_admin_new_submission failed: {e}")


@shared_task(name='verification_gate.notify_admin_monthly_selfie', queue='ai_fast')
def notify_admin_monthly_selfie(selfie_id: str):
    """Notifies admins when a monthly selfie is submitted."""
    from django.contrib.auth import get_user_model
    from .models import MonthlySelfie

    try:
        selfie = MonthlySelfie.objects.get(id=selfie_id)
        seller_name = selfie.verification.full_name or selfie.verification.seller.email
        User = get_user_model()
        admins = User.objects.filter(is_staff=True, is_active=True)

        for admin in admins:
            _send_notification(
                user_id=str(admin.id),
                title="Selfie mensal para rever",
                body=f"{seller_name} submeteu selfie mensal.",
                data={'type': 'monthly_selfie', 'selfie_id': selfie_id}
            )
    except Exception as e:
        logger.error(f"notify_admin_monthly_selfie failed: {e}")


@shared_task(name='verification_gate.notify_verification_approved', queue='ai_fast')
def notify_verification_approved(seller_id: str):
    """Notifies seller that their verification was approved."""
    _send_notification(
        user_id=seller_id,
        title="✅ Verificação aprovada!",
        body="A sua identidade foi verificada. Pode agora vender na MICHA Express.",
        data={'type': 'verification_approved'}
    )


@shared_task(name='verification_gate.notify_verification_rejected', queue='ai_fast')
def notify_verification_rejected(seller_id: str, reason: str, notes: str = ''):
    """Notifies seller that their verification was rejected."""
    reason_labels = {
        'image_unclear': 'Imagem ilegível',
        'id_mismatch': 'Dados não correspondem',
        'id_expired': 'BI expirado',
        'fake_id': 'Documento não reconhecido',
        'selfie_mismatch': 'Selfie não corresponde',
        'incomplete': 'Documentos incompletos',
        'other': 'Outro motivo',
    }
    label = reason_labels.get(reason, reason)
    _send_notification(
        user_id=seller_id,
        title="❌ Verificação rejeitada",
        body=f"Motivo: {label}. Submeta novamente com a correcção necessária.",
        data={'type': 'verification_rejected', 'reason': reason, 'notes': notes}
    )


@shared_task(name='verification_gate.notify_account_locked', queue='ai_fast')
def notify_account_locked(seller_id: str, reason: str):
    """Notifies seller that their account was locked."""
    messages = {
        'bi_expired': (
            "🔒 Conta bloqueada — BI expirado",
            "O seu BI expirou. Submeta um novo BI para reactivar a sua conta."
        ),
        'selfie_overdue': (
            "🔒 Conta bloqueada — Selfie em falta",
            "A sua selfie mensal não foi submetida. Abra a app para reactivar."
        ),
    }
    title, body = messages.get(reason, ("🔒 Conta bloqueada", "Contacte o suporte."))
    _send_notification(
        user_id=seller_id,
        title=title,
        body=body,
        data={'type': 'account_locked', 'reason': reason}
    )


@shared_task(name='verification_gate.send_bi_expiry_alert', queue='ai_fast')
def send_bi_expiry_alert(seller_id: str, days: int):
    """Sends BI expiry warning alert."""
    _send_notification(
        user_id=seller_id,
        title=f"⚠️ BI expira em {days} dias",
        body=f"O seu BI expira em {days} dias. Renove e actualize os seus documentos na app.",
        data={'type': 'bi_expiry_warning', 'days_remaining': days}
    )


@shared_task(name='verification_gate.send_selfie_due_alert', queue='ai_fast')
def send_selfie_due_alert(seller_id: str, days: int):
    """Sends monthly selfie due warning."""
    _send_notification(
        user_id=seller_id,
        title=f"📸 Selfie mensal em {days} dias",
        body=f"A sua selfie mensal deve ser submetida em {days} dias para manter a conta activa.",
        data={'type': 'selfie_due_warning', 'days_remaining': days}
    )


@shared_task(name='verification_gate.notify_selfie_approved', queue='ai_fast')
def notify_selfie_approved(seller_id: str):
    _send_notification(
        user_id=seller_id,
        title="✅ Selfie aprovada",
        body="A sua selfie mensal foi aprovada. Conta activa por mais 30 dias.",
        data={'type': 'selfie_approved'}
    )


@shared_task(name='verification_gate.notify_selfie_rejected', queue='ai_fast')
def notify_selfie_rejected(seller_id: str, reason: str):
    _send_notification(
        user_id=seller_id,
        title="❌ Selfie rejeitada",
        body=f"A sua selfie foi rejeitada: {reason}. Submeta novamente.",
        data={'type': 'selfie_rejected', 'reason': reason}
    )


def _send_notification(user_id: str, title: str, body: str, data: dict = None):
    """Sends push notification via existing notification task."""
    try:
        from apps.ai_engine.tasks import send_push_notification
        send_push_notification.delay(
            user_id=user_id,
            title=title,
            body=body,
            data=data or {},
        )
    except Exception as e:
        logger.debug(f"Push notification failed: {e}")
