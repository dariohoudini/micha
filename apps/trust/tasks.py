"""
apps/trust/tasks.py
"""
from celery import shared_task
import logging
logger = logging.getLogger(__name__)


@shared_task(name='trust.recompute_trust_score', bind=True, max_retries=3, queue='ai_medium')
def recompute_trust_score(self, seller_id: str):
    try:
        from django.contrib.auth import get_user_model
        from .services import TrustScoreService
        User = get_user_model()
        seller = User.objects.get(id=seller_id)
        TrustScoreService.recompute(seller)
    except Exception as exc:
        logger.error(f"Trust score recomputation failed for {seller_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(name='trust.recompute_all_trust_scores', queue='ai_heavy')
def recompute_all_trust_scores():
    """Nightly: recomputes trust scores for all sellers. Scheduled 04:00 WAT."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    sellers = User.objects.filter(is_seller=True, is_active=True)
    for seller in sellers:
        recompute_trust_score.delay(str(seller.id))
    logger.info(f"Queued trust score recomputation for {sellers.count()} sellers")


@shared_task(name='trust.run_fraud_sweep', queue='ai_medium')
def run_fraud_sweep():
    """Daily: runs fraud assessment on all active sellers. Flags high-risk for admin review."""
    from django.contrib.auth import get_user_model
    from .services import FraudDetectionService
    from apps.ai_engine.tasks import send_push_notification

    User = get_user_model()
    sellers = User.objects.filter(is_seller=True, is_active=True)
    flagged = 0
    for seller in sellers:
        try:
            result = FraudDetectionService.assess_seller_risk(seller)
            if result['requires_review']:
                # Notify admin
                admin_users = User.objects.filter(is_staff=True)
                for admin in admin_users:
                    send_push_notification.delay(
                        user_id=str(admin.id),
                        title="Alerta de fraude",
                        body=f"Vendedor {seller.email} requer revisão (risco: {result['risk_level']})",
                        data={'type': 'fraud_alert', 'seller_id': str(seller.id)}
                    )
                flagged += 1
        except Exception as e:
            logger.debug(f"Fraud sweep error for {seller.id}: {e}")

    logger.info(f"Fraud sweep complete: {flagged} sellers flagged for review")
