from celery import shared_task

@shared_task(name='verification.send_selfie_reminders')
def send_selfie_reminders():
    """Daily: remind verified sellers to update their selfie if it's been 30+ days."""
    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils import timezone
        User = get_user_model()
        sellers = User.objects.filter(is_seller=True, is_verified_seller=True, is_active=True)
        count = 0
        for seller in sellers:
            try:
                from apps.verification.models import SellerVerification
                verif = SellerVerification.objects.get(seller=seller)
                age = (timezone.now() - verif.approved_at).days if verif.approved_at else 0
                if age >= 30 and age % 30 == 0:
                    send_mail(
                        subject='MICHA: Please update your seller selfie',
                        message=(
                            f'Hi,\n\nPlease log in and upload a fresh selfie to keep '
                            f'your verified seller status active.\n\n'
                            f'Go to: {settings.FRONTEND_URL}/seller/verification/\n\n'
                            f'— MICHA Team'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[seller.email],
                        fail_silently=True,
                    )
                    count += 1
            except Exception:
                pass
        return f"Sent selfie reminders to {count} sellers"
    except Exception as e:
        return f"Error: {e}"

from celery import shared_task
from django.utils import timezone

@shared_task(name='verification.suspend_expired_kyc')
def suspend_expired_kyc():
    """
    T&C §3.4 — suspend sellers whose KYC document has expired.
    Runs daily. Sets verification status to expired and suspends seller.
    """
    from apps.verification.models import SellerVerification
    from django.contrib.auth import get_user_model
    User = get_user_model()

    today = timezone.now().date()
    expired = SellerVerification.objects.filter(
        status='approved',
        id_expiry_date__lt=today,
    )
    suspended_count = 0
    for verification in expired:
        verification.status = 'expired'
        verification.save(update_fields=['status'])
        user = verification.seller
        user.is_verified_seller = False
        user.status = 'suspended'
        user.save(update_fields=['is_verified_seller', 'status'])
        suspended_count += 1

    return f'Suspended {suspended_count} sellers with expired KYC'
