from rest_framework import serializers
from django.core.exceptions import ValidationError
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
    # Fields the admin KYC console reads. The raw ImageField serialises to a
    # relative path and the FK to just an id, so the admin UI (which expects
    # ``id_document_url`` / ``seller_email`` / ``submitted_at``) showed nothing.
    seller_email = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()
    id_document_url = serializers.SerializerMethodField()
    id_document_back_url = serializers.SerializerMethodField()
    selfie_url = serializers.SerializerMethodField()

    class Meta:
        model = SellerVerification
        fields = [
            # Model field is ``seller`` (OneToOne FK to User), not
            # ``user`` — this serializer previously referenced ``user``
            # which is not on the model, raising ImproperlyConfigured.
            # The ``apply/`` view was therefore 500-ing every submit.
            'id', 'seller', 'id_number', 'id_expiry_date',
            'id_document', 'selfie', 'status', 'rejection_reason',
            # 'last_selfie_update' removed — not present on the
            # SellerVerification model; would raise
            # ImproperlyConfigured on every instantiation.
            'is_id_expired', 'needs_selfie_update',
            'id_validation_error', 'created_at', 'updated_at', 'logs',
            'seller_email', 'submitted_at', 'id_document_url',
            'id_document_back_url', 'selfie_url',
            # AliExpress §4.2 — business-account additional documents.
            'business_licence', 'bank_proof', 'power_of_attorney',
            'id_document_back', 'is_business_account',
        ]
        read_only_fields = [
            'seller', 'status', 'rejection_reason',
            'created_at', 'updated_at',
        ]

    def get_is_id_expired(self, obj):
        # The model has no is_id_expired() method — compute from the stored
        # expiry date. A missing date is treated as "not expired" so the
        # admin list never crashes on a partially-filled record.
        if not obj.id_expiry_date:
            return False
        return obj.id_expiry_date <= timezone.now().date()

    def get_needs_selfie_update(self, obj):
        # No last_selfie_update field on the model → nothing to compare
        # against. Kept for API shape; always False until periodic
        # re-verification is implemented.
        return False

    def get_id_validation_error(self, obj):
        # Surface a BI-format problem to the admin reviewer without crashing
        # the list. Decrypting id_number can raise if the key rotated, so
        # guard everything.
        try:
            value = obj.id_number
            if not value:
                return None
            validate_angolan_bi(value)
        except ValidationError as exc:
            return exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
        except Exception:
            return None
        return None

    def get_seller_email(self, obj):
        return getattr(obj.seller, 'email', None)

    def get_submitted_at(self, obj):
        return obj.created_at

    def _abs(self, filefield):
        """Absolute media URL so the mobile WebView can load it from Django
        (its own origin can't serve /media/)."""
        if not filefield:
            return None
        try:
            url = filefield.url
        except ValueError:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url

    def get_id_document_url(self, obj):
        return self._abs(obj.id_document)

    def get_id_document_back_url(self, obj):
        return self._abs(obj.id_document_back)

    def get_selfie_url(self, obj):
        return self._abs(obj.selfie)

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
