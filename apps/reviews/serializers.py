from rest_framework import serializers
from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.ReadOnlyField(source="reviewer.email")

    class Meta:
        model = Review
        fields = (
            "id",
            "reviewer_email",
            "seller",
            "rating",
            "comment",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate(self, attrs):
        request = self.context["request"]
        if request.user == attrs["seller"]:
            raise serializers.ValidationError("You cannot review yourself.")
        return attrs

    def create(self, validated_data):
        validated_data["reviewer"] = self.context["request"].user
        return super().create(validated_data)
