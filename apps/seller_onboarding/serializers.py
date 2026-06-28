"""
Serializers for the seller onboarding REST surface.

These are intentionally thin — most validation lives in services.py
so it's reachable from Celery tasks and admin actions too.
"""
from rest_framework import serializers

from .models import (
    KycDocument, SellerAgreement, SellerApplication, SellerBrand,
    SellerCategoryEnrolment, SellerCategoryUpgradeRequest,
    SellerCertificate, SellerFeeInvoice, SellerHealthScore,
    SellerHolidayLog, SellerLead, SellerOnboardingEvent,
    SellerReactivationRequest, SellerTierHistory, SellerTierState,
    SellerTrainingProgress,
)


class SellerLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerLead
        fields = [
            'id', 'lead_source', 'referral_code', 'company_name',
            'contact_name', 'contact_email', 'contact_phone',
            'country', 'primary_category', 'estimated_sku_count',
            'annual_revenue_bracket', 'has_brand', 'current_platforms',
            'utm_source', 'utm_medium', 'utm_campaign',
            'status', 'qualification_score', 'qualification_breakdown',
            'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'qualification_score',
            'qualification_breakdown', 'created_at',
        ]


class SellerApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerApplication
        fields = [
            'id', 'lead', 'applicant_email', 'status', 'company_name',
            'country', 'business_reg_number', 'legal_representative_name',
            'legal_representative_id_type', 'contact_phone',
            'primary_category_id', 'return_address',
            'estimated_monthly_orders', 'referral_code',
            'eligibility_passed', 'eligibility_failure_code',
            'kyc_score', 'submitted_at', 'reviewed_at', 'approved_at',
            'rejection_reason', 'rejection_codes', 'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'eligibility_passed',
            'eligibility_failure_code', 'kyc_score',
            'submitted_at', 'reviewed_at', 'approved_at',
            'rejection_reason', 'rejection_codes', 'created_at',
        ]


class KycDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycDocument
        fields = [
            'id', 'application', 'document_type', 'file_key', 'status',
            'ocr_fields', 'ocr_confidence', 'discrepancies',
            'liveness_score', 'face_match_score',
            'ocr_completed_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'ocr_fields', 'ocr_confidence',
            'discrepancies', 'liveness_score', 'face_match_score',
            'ocr_completed_at', 'created_at',
        ]


class SellerAgreementSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerAgreement
        fields = [
            'id', 'application', 'status', 'expires_at',
            'signed_at', 'signature_name', 'signature_hash',
            'scroll_completion_pct', 'created_at',
        ]
        read_only_fields = fields


class SellerFeeInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerFeeInvoice
        fields = [
            'id', 'application', 'base_amount', 'discounts',
            'final_amount', 'currency', 'status', 'due_at',
            'paid_at', 'paid_amount', 'payment_reference',
            'created_at',
        ]
        read_only_fields = fields


class SellerCategoryEnrolmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerCategoryEnrolment
        fields = [
            'id', 'category_id', 'enrolment_type', 'status',
            'documents_submitted', 'rejection_reason',
            'approved_at', 'expires_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'rejection_reason', 'approved_at',
            'expires_at', 'created_at',
        ]


class SellerCategoryUpgradeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerCategoryUpgradeRequest
        fields = '__all__'
        read_only_fields = [
            'id', 'metrics_snapshot', 'status', 'reviewer',
            'decision_notes', 'created_at', 'decided_at',
        ]


class SellerBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerBrand
        fields = '__all__'
        read_only_fields = [
            'id', 'status', 'verified_at', 'expires_at',
            'rejection_reason', 'created_at',
        ]


class SellerTierStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerTierState
        fields = [
            'current_tier', 'pending_tier', 'last_score',
            'last_metrics', 'tier_updated_at',
            'downgrade_warning_sent_at',
        ]
        read_only_fields = fields


class SellerTierHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerTierHistory
        fields = [
            'id', 'old_tier', 'new_tier', 'computed_score',
            'metrics_snapshot', 'effective_date',
        ]


class SellerHealthScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerHealthScore
        fields = [
            'snapshot_date', 'score', 'intervention_band',
            'feedback_component', 'dispute_component',
            'shipping_component', 'response_component',
            'listing_quality_component', 'returns_component',
        ]


class SellerTrainingProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerTrainingProgress
        fields = [
            'module_id', 'status', 'progress_pct',
            'quiz_attempts', 'quiz_score', 'passed',
            'started_at', 'completed_at',
        ]


class SellerCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerCertificate
        fields = [
            'id', 'module_id', 'certificate_type',
            'issued_at', 'expires_at', 'verification_url',
            'certificate_hash',
        ]


class SellerHolidayLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerHolidayLog
        fields = [
            'id', 'start_date', 'end_date', 'reason',
            'message_to_buyers', 'activated_at', 'deactivated_at',
            'early_deactivated',
        ]


class SellerReactivationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerReactivationRequest
        fields = '__all__'
        read_only_fields = [
            'id', 'status', 'reviewer', 'decision_notes',
            'created_at', 'decided_at',
        ]


class SellerOnboardingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerOnboardingEvent
        fields = ['id', 'kind', 'payload', 'created_at',
                  'application', 'seller']
