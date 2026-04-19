"""
Celery Configuration
FIX: All critical tasks have idempotency cache locks
     Prevents double-crediting sellers if task runs twice
"""
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("micha")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Recommendations
    "precompute-user-feeds": {"task": "recommendations.precompute_user_feeds", "schedule": crontab(minute="*/30"), "options": {"queue": "low"}},
    "check-price-alerts": {"task": "recommendations.check_price_alerts", "schedule": crontab(minute="*/30"), "options": {"queue": "default"}},
    "check-back-in-stock": {"task": "recommendations.check_back_in_stock", "schedule": crontab(minute="*/15"), "options": {"queue": "default"}},
    "recalculate-similarity": {"task": "recommendations.recalculate_similarity", "schedule": crontab(hour=2, minute=0), "options": {"queue": "low"}},
    "weekly-digest": {"task": "recommendations.weekly_digest", "schedule": crontab(day_of_week=0, hour=10, minute=0), "options": {"queue": "low"}},
    # Cleanup
    "cleanup-browsing-sessions": {"task": "recommendations.cleanup_browsing_sessions", "schedule": crontab(hour=4, minute=0), "options": {"queue": "low"}},
    "cleanup-stock-urgency": {"task": "recommendations.cleanup_stock_urgency", "schedule": crontab(minute="*/5")},
    # Payments
    "release-held-earnings": {"task": "payments.release_held_earnings", "schedule": crontab(minute=0), "options": {"queue": "high"}},
    # Orders
    "auto-complete-orders": {"task": "orders.auto_complete_old_orders", "schedule": crontab(hour=1, minute=0)},
    # Inventory
    "clean-stock-reservations": {"task": "inventory.clean_expired_reservations", "schedule": crontab(minute="*/5")},
    "low-stock-alerts": {"task": "inventory.send_low_stock_alerts", "schedule": crontab(hour=8, minute=0)},
    # Analytics
    "update-seller-performance": {"task": "analytics.update_seller_performance_scores", "schedule": crontab(minute=0, hour="*/6"), "options": {"queue": "low"}},
    "cleanup-funnel-events": {"task": "analytics.cleanup_old_funnel_events", "schedule": crontab(hour=5, minute=0), "options": {"queue": "low"}},
    # Collections
    "record-price-history": {"task": "collections.record_price_history", "schedule": crontab(hour=0, minute=30), "options": {"queue": "low"}},
    # Users
    "delete-scheduled-accounts": {"task": "users.delete_scheduled_accounts", "schedule": crontab(hour=3, minute=0), "options": {"queue": "low"}},
    "cleanup-activity-logs": {"task": "users.cleanup_old_activity_logs", "schedule": crontab(hour=5, minute=30), "options": {"queue": "low"}},
    # Verification
    "selfie-reminders": {"task": "verification.send_selfie_reminders", "schedule": crontab(hour=9, minute=0), "options": {"queue": "low"}},
    # OTP cleanup — delete expired OTP hashes every hour
    "cleanup-expired-otps": {"task": "users.cleanup_expired_otps", "schedule": crontab(minute=0)},
}
