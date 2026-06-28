from django.contrib import admin

from .models import (
    AgreementTemplate, KycDocument, SellerAdCredit, SellerAgreement,
    SellerApplication, SellerBrand, SellerCategoryEnrolment,
    SellerCategoryUpgradeRequest, SellerCertificate,
    SellerCommissionOverride, SellerFeeInvoice, SellerHealthScore,
    SellerHolidayLog, SellerLead, SellerOnboardingEvent,
    SellerReactivationRequest, SellerTierHistory, SellerTierState,
    SellerTrainingProgress, SellerVisibilityBoost,
)


@admin.register(SellerLead)
class SellerLeadAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'country', 'status',
                    'qualification_score', 'created_at')
    list_filter = ('status', 'lead_source', 'country')
    search_fields = ('company_name', 'contact_email', 'contact_name')
    readonly_fields = ('id', 'qualification_score',
                       'qualification_breakdown', 'created_at')


@admin.register(SellerApplication)
class SellerApplicationAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'country', 'status', 'submitted_at',
                    'kyc_score', 'approved_at')
    list_filter = ('status', 'country', 'eligibility_passed')
    search_fields = ('company_name', 'applicant_email', 'business_reg_number')
    readonly_fields = ('id', 'created_at', 'updated_at',
                       'submitted_at', 'reviewed_at', 'approved_at',
                       'eligibility_passed', 'eligibility_failure_code')


@admin.register(KycDocument)
class KycDocumentAdmin(admin.ModelAdmin):
    list_display = ('application', 'document_type', 'status',
                    'ocr_confidence', 'created_at')
    list_filter = ('status', 'document_type')


@admin.register(AgreementTemplate)
class AgreementTemplateAdmin(admin.ModelAdmin):
    list_display = ('version', 'effective_date', 'requires_re_sign')
    list_filter = ('requires_re_sign',)


@admin.register(SellerAgreement)
class SellerAgreementAdmin(admin.ModelAdmin):
    list_display = ('application', 'status', 'signed_at', 'expires_at')
    list_filter = ('status',)
    readonly_fields = ('signature_hash', 'signing_token')


@admin.register(SellerFeeInvoice)
class SellerFeeInvoiceAdmin(admin.ModelAdmin):
    list_display = ('application', 'final_amount', 'currency',
                    'status', 'due_at', 'paid_at')
    list_filter = ('status', 'currency')


@admin.register(SellerTierState)
class SellerTierStateAdmin(admin.ModelAdmin):
    list_display = ('seller', 'current_tier', 'pending_tier',
                    'last_score', 'tier_updated_at')
    list_filter = ('current_tier',)


@admin.register(SellerTierHistory)
class SellerTierHistoryAdmin(admin.ModelAdmin):
    list_display = ('seller', 'old_tier', 'new_tier',
                    'computed_score', 'effective_date')


@admin.register(SellerHealthScore)
class SellerHealthScoreAdmin(admin.ModelAdmin):
    list_display = ('seller', 'snapshot_date', 'score', 'intervention_band')
    list_filter = ('intervention_band',)


@admin.register(SellerBrand)
class SellerBrandAdmin(admin.ModelAdmin):
    list_display = ('brand_name', 'seller', 'brand_type', 'status',
                    'verified_at', 'expires_at')
    list_filter = ('status', 'brand_type')


@admin.register(SellerCategoryEnrolment)
class SellerCategoryEnrolmentAdmin(admin.ModelAdmin):
    list_display = ('seller', 'category_id', 'enrolment_type', 'status')
    list_filter = ('status', 'enrolment_type')


@admin.register(SellerCategoryUpgradeRequest)
class SellerCategoryUpgradeRequestAdmin(admin.ModelAdmin):
    list_display = ('seller', 'current_category_id', 'target_category_id',
                    'status', 'created_at')
    list_filter = ('status',)


@admin.register(SellerTrainingProgress)
class SellerTrainingProgressAdmin(admin.ModelAdmin):
    list_display = ('seller', 'module_id', 'status',
                    'progress_pct', 'quiz_score', 'passed')
    list_filter = ('status', 'module_id', 'passed')


@admin.register(SellerCertificate)
class SellerCertificateAdmin(admin.ModelAdmin):
    list_display = ('seller', 'module_id', 'certificate_type', 'issued_at')


@admin.register(SellerVisibilityBoost)
class SellerVisibilityBoostAdmin(admin.ModelAdmin):
    list_display = ('seller', 'boost_type', 'boost_multiplier', 'valid_until')


@admin.register(SellerAdCredit)
class SellerAdCreditAdmin(admin.ModelAdmin):
    list_display = ('seller', 'amount', 'currency', 'spent_amount', 'valid_until')


@admin.register(SellerCommissionOverride)
class SellerCommissionOverrideAdmin(admin.ModelAdmin):
    list_display = ('seller', 'rate', 'reason', 'valid_until')


@admin.register(SellerHolidayLog)
class SellerHolidayLogAdmin(admin.ModelAdmin):
    list_display = ('seller', 'start_date', 'end_date',
                    'activated_at', 'deactivated_at')


@admin.register(SellerReactivationRequest)
class SellerReactivationRequestAdmin(admin.ModelAdmin):
    list_display = ('seller', 'suspension_reason', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(SellerOnboardingEvent)
class SellerOnboardingEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'application', 'seller', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at', 'application',
                       'seller', 'actor')
    search_fields = ('kind',)


# ─── CH6/13/17/19/21/22/24 extras ────────────────────────────────

from .models import (
    AcquisitionFunnelSnapshot, ChoiceEnrolment, ChoiceWarehouse,
    FeeRebate, OfficialBrandStoreApplication, SellerApiApp,
    SellerApiAuthorisation, SellerApiKey,
    SellerDeregistrationRequest, SellerEmailLog, SellerStoreType,
    SellerWebhookDelivery, SellerWebhookEndpoint,
)


@admin.register(SellerEmailLog)
class SellerEmailLogAdmin(admin.ModelAdmin):
    list_display = ('seller', 'sequence_key', 'status',
                    'suppression_reason', 'queued_at', 'sent_at')
    list_filter = ('status', 'sequence_key')
    search_fields = ('to_email',)


@admin.register(SellerStoreType)
class SellerStoreTypeAdmin(admin.ModelAdmin):
    list_display = ('seller', 'store_type', 'search_multiplier',
                    'is_pinned', 'updated_at')
    list_filter = ('store_type', 'is_pinned')


@admin.register(OfficialBrandStoreApplication)
class OfficialBrandStoreApplicationAdmin(admin.ModelAdmin):
    list_display = ('seller', 'brand', 'status', 'created_at', 'decided_at')
    list_filter = ('status',)


@admin.register(FeeRebate)
class FeeRebateAdmin(admin.ModelAdmin):
    list_display = ('seller', 'fee_period_start', 'gmv_usd',
                    'rebate_pct', 'rebate_amount', 'status')
    list_filter = ('status', 'rebate_pct')


@admin.register(SellerApiKey)
class SellerApiKeyAdmin(admin.ModelAdmin):
    list_display = ('seller', 'label', 'key_prefix', 'is_active',
                    'expires_at', 'last_used_at')
    list_filter = ('is_active',)
    readonly_fields = ('key_hash', 'key_prefix')


@admin.register(SellerApiApp)
class SellerApiAppAdmin(admin.ModelAdmin):
    list_display = ('name', 'client_id', 'is_active', 'created_at')
    list_filter = ('is_active',)


@admin.register(SellerApiAuthorisation)
class SellerApiAuthorisationAdmin(admin.ModelAdmin):
    list_display = ('seller', 'app', 'access_expires_at',
                    'refresh_expires_at', 'revoked_at')


@admin.register(SellerWebhookEndpoint)
class SellerWebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ('seller', 'url', 'is_active',
                    'consecutive_failures', 'created_at')
    list_filter = ('is_active',)


@admin.register(SellerWebhookDelivery)
class SellerWebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'event_type', 'attempt',
                    'response_status', 'delivered_at', 'created_at')
    list_filter = ('event_type',)


@admin.register(SellerDeregistrationRequest)
class SellerDeregistrationRequestAdmin(admin.ModelAdmin):
    list_display = ('seller', 'status', 'requested_at',
                    'effective_at', 'completed_at')
    list_filter = ('status',)


@admin.register(ChoiceWarehouse)
class ChoiceWarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'country', 'capacity_units', 'is_active')


@admin.register(ChoiceEnrolment)
class ChoiceEnrolmentAdmin(admin.ModelAdmin):
    list_display = ('seller', 'warehouse', 'status',
                    'estimated_monthly_units', 'activated_at')
    list_filter = ('status',)


@admin.register(AcquisitionFunnelSnapshot)
class AcquisitionFunnelSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'leads_submitted',
                    'applications_submitted', 'kyc_approved', 'activated')
