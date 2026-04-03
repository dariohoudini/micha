from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class AdminAction(models.Model):
    ACTIONS = (
        ("warn", "Warn"),
        ("suspend", "Suspend"),
        ("ban", "Ban"),
    )

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="actions_taken")
    target = models.ForeignKey(User, on_delete=models.CASCADE, related_name="actions_received")

    action = models.CharField(max_length=10, choices=ACTIONS)
    reason = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} → {self.target}"
