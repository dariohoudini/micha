from rest_framework import generics, permissions, status, serializers
from rest_framework.response import Response
from django.db import models
from apps.stores.models import Store
from apps.users.permissions import IsNotSuspended

from .models import Chat, Message
from .serializers import ChatSerializer, MessageSerializer



# -----------------------------
# Chat Views
# -----------------------------

class ConversationListCreateView(generics.ListCreateAPIView):
    """
    GET: list all chats of the current user
    POST: create a new chat between buyer and seller
    """
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        user = self.request.user
        return Chat.objects.filter(models.Q(buyer=user) | models.Q(seller=user))

    def perform_create(self, serializer):
        buyer = self.request.user
        seller_id = self.request.data.get('seller_id')

        try:
            seller = Store.objects.get(id=seller_id).owner
        except Store.DoesNotExist:
            raise serializers.ValidationError({"seller_id": "Seller not found."})

        chat, created = Chat.objects.get_or_create(buyer=buyer, seller=seller)
        return chat  # DRF handles returning the serializer instance


class MessageListCreateView(generics.ListCreateAPIView):
    """
    GET: list all messages in a conversation
    POST: create/send a message
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        conversation_id = self.kwargs.get("conversation_id")
        try:
            chat = Chat.objects.get(id=conversation_id)
        except Chat.DoesNotExist:
            return Message.objects.none()
        user = self.request.user
        if user != chat.buyer and user != chat.seller:
            return Message.objects.none()
        return Message.objects.filter(chat=chat).order_by("created_at")

    def perform_create(self, serializer):
        conversation_id = self.kwargs.get("conversation_id")
        try:
            chat = Chat.objects.get(id=conversation_id)
        except Chat.DoesNotExist:
            raise serializers.ValidationError({"chat_id": "Chat not found."})

        if self.request.user != chat.buyer and self.request.user != chat.seller:
            raise serializers.ValidationError({"detail": "You are not a participant of this chat."})

        serializer.save(chat=chat, sender=self.request.user)
