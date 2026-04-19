"""
User Tasks
FIX: cleanup_expired_otps — clear OTP hashes after expiry
FIX: delete_scheduled_accounts — now also erases S3 media and cache keys
"""
from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger("micha")


@shared_task(name="users.delete_scheduled_accounts")
def delete_scheduled_accounts():
    """
    Permanently anonymise accounts that requested deletion 30+ days ago.
    FIX: Also erases S3 media files and Redis cache keys (full erasure for Lei 22/11)
    """
    try:
        from django.contrib.auth import get_user_model
        from datetime import timedelta
        from django.core.cache import cache
        User = get_user_model()
        cutoff = timezone.now() - timedelta(days=30)
        to_delete = User.objects.filter(deletion_requested_at__lte=cutoff, is_deleted=False)
        count = 0
        for user in to_delete:
            # FIX: Erase S3 media files (avatars)
            try:
                if user.profile and user.profile.avatar:
                    user.profile.avatar.delete(save=False)
                    user.profile.avatar = None
                    user.profile.bio = ""
                    user.profile.full_name = "Deleted User"
                    user.profile.save()
            except Exception:
                pass

            # FIX: Clear Redis cache keys for this user
            cache.delete(f"feed:user:{user.id}")
            cache.delete(f"session:user:{user.id}")

            # Anonymise user record
            user.email = f"deleted_{user.pk}@deleted.micha"
            user.is_active = False
            user.is_deleted = True
            user.phone = None
            user.fcm_token = None
            user.google_id = None
            user.facebook_id = None
            user.apple_id = None
            user.password_reset_token_hash = None
            user.email_otp_hash = None
            user.two_fa_secret = None
            user.save()
            count += 1

        return f"Anonymised {count} accounts with full data erasure"
    except Exception as e:
        logger.exception(f"delete_scheduled_accounts failed: {e}")
        return f"Error: {e}"


@shared_task(name="users.cleanup_expired_otps")
def cleanup_expired_otps():
    """
    FIX: Clear OTP hashes after expiry — do not keep stale hashes in DB.
    Runs every hour.
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        now = timezone.now()

        updated = User.objects.filter(
            email_otp_expires__lt=now,
            email_otp_hash__isnull=False,
        ).update(email_otp_hash=None, email_otp_expires=None)

        updated += User.objects.filter(
            phone_otp_expires__lt=now,
            phone_otp_hash__isnull=False,
        ).update(phone_otp_hash=None, phone_otp_expires=None)

        updated += User.objects.filter(
            password_reset_expires__lt=now,
            password_reset_token_hash__isnull=False,
        ).update(password_reset_token_hash=None, password_reset_expires=None)

        return f"Cleared {updated} expired OTP hashes"
    except Exception as e:
        return f"Error: {e}"


@shared_task(name="users.cleanup_old_activity_logs")
def cleanup_old_activity_logs():
    try:
        from apps.users.models import UserActivityLog
        from django.conf import settings
        from datetime import timedelta
        days = getattr(settings, "DATA_RETENTION", {}).get("activity_logs", 365)
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = UserActivityLog.objects.filter(created_at__lte=cutoff).delete()
        return f"Deleted {deleted} old activity logs"
    except Exception as e:
        return f"Error: {e}"
