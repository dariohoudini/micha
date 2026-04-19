from celery import shared_task

@shared_task(name='verification.send_selfie_reminders')
def send_selfie_reminders():
    """Daily: remind verified sellers to update their selfie if it's been 30+ days."""
    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta
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
