from rest_framework import serializers
from .models import ContentFlag, IPBan, BuyerProtectionClaim


class ContentFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentFlag
        fields = ["id", "target_type", "target_id", "reason", "auto_flagged", "is_resolved", "created_at"]
        read_only_fields = ["id", "created_at"]


class IPBanSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPBan
        fields = ["id", "ip_address", "reason", "created_at"]
        read_only_fields = ["id", "created_at"]


class BuyerProtectionClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerProtectionClaim
        fields = ["id", "order", "reason", "status", "auto_approved", "resolved_at", "created_at"]
        read_only_fields = ["id", "status", "auto_approved", "resolved_at", "created_at"]
