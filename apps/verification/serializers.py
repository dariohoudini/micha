from rest_framework import serializers
from .models import SellerVerification
from django.utils import timezone


class SellerVerificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = SellerVerification
        fields = (
            'id_number',
            'id_expiry_date',
            'id_document',
            'selfie',
        )

    def validate(self, data):
        if data['id_expiry_date'] < timezone.now().date():
            raise serializers.ValidationError("ID is expired.")
        return data
