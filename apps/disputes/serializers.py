from rest_framework import serializers
from .models import Dispute, DisputeMessage, FraudFlag


class DisputeMessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.ReadOnlyField(source="sender.email")

    class Meta:
        model = DisputeMessage
        fields = ["id", "sender_email", "message", "attachment", "created_at"]
        read_only_fields = ["id", "created_at"]


class DisputeSerializer(serializers.ModelSerializer):
    messages = DisputeMessageSerializer(many=True, read_only=True)
    buyer_email = serializers.ReadOnlyField(source="buyer.email")
    seller_email = serializers.ReadOnlyField(source="seller.email")

    class Meta:
        model = Dispute
        fields = [
            "id", "order", "buyer_email", "seller_email", "reason",
            "description", "status", "admin_note", "resolution",
            "messages", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "admin_note", "resolution", "created_at", "updated_at"]


class FraudFlagSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source="user.email")

    class Meta:
        model = FraudFlag
        fields = ["id", "user_email", "reason", "details", "is_resolved", "created_at"]
        read_only_fields = ["id", "created_at"]
