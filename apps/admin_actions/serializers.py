from rest_framework import serializers
from .models import AdminAction


class AdminActionSerializer(serializers.ModelSerializer):
    admin_email = serializers.ReadOnlyField(source="admin.email")

    class Meta:
        model = AdminAction
        fields = (
            "id",
            "admin_email",
            "target",
            "action",
            "reason",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["admin"] = request.user
        return super().create(validated_data)
