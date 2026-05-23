from rest_framework import serializers
from .models import ContentFlag, IPBan, BuyerProtectionClaim


class ContentFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentFlag
        fields = ["id", "target_type", "target_id", "reason", "auto_flagged", "is_resolved", "created_at"]
        read_only_fields = ["id", "created_at"]


class ModerationQueueItemSerializer(serializers.ModelSerializer):
    """Queue row representation for the moderator dashboard.

    Wider than ContentFlagSerializer — includes the new R4 state fields
    + denormalised owner email + a short content snippet for the target.
    The snippet is computed in ``views.py`` and injected as a context
    field so the serializer stays cheap (one model + a dict lookup).
    """
    target_user_email = serializers.SerializerMethodField()
    flagger_email = serializers.SerializerMethodField()
    resolved_by_email = serializers.SerializerMethodField()
    target_snippet = serializers.SerializerMethodField()

    class Meta:
        model = ContentFlag
        fields = [
            "id", "target_type", "target_id", "target_user_email",
            "flagger_email", "reason", "severity", "status",
            "auto_flagged", "target_snippet",
            "resolved_by_email", "resolved_at", "resolution_note",
            "created_at",
        ]
        read_only_fields = fields

    def get_target_user_email(self, obj):
        u = obj.target_user
        return getattr(u, 'email', None) if u else None

    def get_flagger_email(self, obj):
        u = obj.flagger
        return getattr(u, 'email', None) if u else None

    def get_resolved_by_email(self, obj):
        u = obj.resolved_by
        return getattr(u, 'email', None) if u else None

    def get_target_snippet(self, obj):
        snippets = (self.context or {}).get('snippets') or {}
        return snippets.get((obj.target_type, obj.target_id), '')


class ModerationDecisionSerializer(serializers.Serializer):
    """Input payload for approve / reject / escalate endpoints."""
    note = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=2000,
    )


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
