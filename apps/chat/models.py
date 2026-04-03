from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Chat(models.Model):
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats_as_buyer')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats_as_seller')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat: {self.buyer.phone} ↔ {self.seller.phone}"


class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.sender.phone}: {self.content[:20]}"
