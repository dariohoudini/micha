from rest_framework import serializers
from .models import Chat, Message


# -----------------------------
# Chat serializer
# -----------------------------
class ChatSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source="buyer.username", read_only=True)
    seller_name = serializers.CharField(source="seller.username", read_only=True)

    class Meta:
        model = Chat
        fields = [
            "id",
            "buyer",
            "buyer_name",
            "seller",
            "seller_name",
            "created_at",
        ]
        read_only_fields = ["id", "buyer_name", "seller_name", "created_at"]


# -----------------------------
# Message serializer
# -----------------------------
class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "chat",
            "sender",
            "sender_name",
            "content",
            "created_at",
        ]
        read_only_fields = ["id", "sender_name", "created_at"]

    def create(self, validated_data):
        """
        Ensure sender is automatically set to the request user.
        """
        if "sender" not in validated_data:
            raise serializers.ValidationError("Sender must be provided")
        return super().create(validated_data)
