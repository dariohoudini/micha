from rest_framework import serializers
from django.utils import timezone
from .models import SellerVerification, VerificationLog, validate_angolan_bi


class VerificationLogSerializer(serializers.ModelSerializer):
    performed_by_email = serializers.ReadOnlyField(source='performed_by.email')

    class Meta:
        model = VerificationLog
        fields = ['id', 'action', 'note', 'performed_by_email', 'created_at']


class SellerVerificationSerializer(serializers.ModelSerializer):
    logs = VerificationLogSerializer(many=True, read_only=True)
    is_id_expired = serializers.SerializerMethodField()
    needs_selfie_update = serializers.SerializerMethodField()
    id_validation_error = serializers.SerializerMethodField()

    class Meta:
        model = SellerVerification
        fields = [
            'id', 'user', 'id_number', 'id_expiry_date',
            'id_document', 'selfie', 'status', 'rejection_reason',
            'last_selfie_update', 'is_id_expired', 'needs_selfie_update',
            'id_validation_error', 'created_at', 'updated_at', 'logs',
        ]
        read_only_fields = [
            'user', 'status', 'rejection_reason',
            'last_selfie_update', 'created_at', 'updated_at',
        ]

    def get_is_id_expired(self, obj):
        return obj.is_id_expired()

    def get_needs_selfie_update(self, obj):
        return obj.needs_selfie_update()

    def get_id_validation_error(self, obj):
        return obj.get_id_validation_error()

    def validate_id_number(self, value):
        """Validate Angolan BI number format on submission."""
        is_valid, message = validate_angolan_bi(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value.strip().upper()

    def validate_id_expiry_date(self, value):
        if value <= timezone.now().date():
            raise serializers.ValidationError(
                "ID document is already expired. Please use a valid ID."
            )
        return value


class SelfieUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerVerification
        fields = ['selfie']

    def update(self, instance, validated_data):
        instance.selfie = validated_data['selfie']
        instance.last_selfie_update = timezone.now()
        instance.save()
        return instance


class AdminVerificationActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=['approved', 'rejected', 'suspended', 'expired']
    )
    note = serializers.CharField(required=False, allow_blank=True)
