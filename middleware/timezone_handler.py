"""
Angola Timezone Middleware
FIX: All timestamps stored in UTC but Angola is UTC+1 (Africa/Luanda).
This middleware activates the correct timezone based on the user preference
or defaults to Africa/Luanda for Angola-based users.
"""
import zoneinfo
from django.utils import timezone


class TimezoneMiddleware:
    """
    Activate user timezone for each request.
    Stored timestamps are always UTC — this just controls display.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Try to get timezone from user preferences
        tzname = None

        if request.user.is_authenticated:
            try:
                tzname = getattr(request.user, "timezone", None) or "Africa/Luanda"
            except Exception:
                tzname = "Africa/Luanda"
        else:
            # Default to Angola timezone
            tzname = request.META.get("HTTP_X_TIMEZONE", "Africa/Luanda")

        try:
            tz = zoneinfo.ZoneInfo(tzname)
            timezone.activate(tz)
        except (zoneinfo.ZoneInfoNotFoundError, Exception):
            timezone.activate(zoneinfo.ZoneInfo("Africa/Luanda"))

        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
