from django.contrib import admin

from .models import (
    AccountTakeoverCase, AgeGateChallenge, AgeGatedCategory,
    AppealDecision, AppealRequest, BanEvasionSignal,
    BlacklistCheck, BrandKeywordWatch, BuyerFraudRing,
    BuyerFraudRingMember, BuyerTrustScore, CounterfeitCase,
    CounterfeitSignal, CoordinatedBuyingRing, CsamHashEntry,
    CsamIncident, DmcaCounterNotice, DmcaNotice,
    EnhancedDueDiligenceReview, ExportControlListing,
    HateSpeechDetection, HateSpeechEnforcement, ImpersonationCheck,
    IpComplaint, IpComplaintResponse, IpRightsHolder,
    LawEnforcementRequest, LegalHold, ManipulationFlag,
    PriceGougingFlag, ProductRecall, ProhibitedItemDetection,
    ProhibitedItemRule, RecallNotification, RefundFarmingCase,
    ReviewAuthenticitySignal, ReviewFraudRing,
    SellerBlacklistEntry, SerialDisputerSignal, TrustSafetyEvent,
    TrustSafetyKpiSnapshot, TsDecision, TsModel, UserBlock,
    UserReport,
)


@admin.register(TsModel)
class TsModelAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'kind', 'version',
                    'confidence_threshold', 'is_active')
    list_filter = ('kind', 'is_active')


@admin.register(TsDecision)
class TsDecisionAdmin(admin.ModelAdmin):
    list_display = ('model', 'surface', 'subject_kind',
                    'subject_id', 'confidence', 'outcome', 'decided_at')
    list_filter = ('outcome', 'surface', 'subject_kind')


@admin.register(ProhibitedItemRule)
class ProhibitedItemRuleAdmin(admin.ModelAdmin):
    list_display = ('code', 'category', 'enforcement',
                    'severity', 'is_active')
    list_filter = ('category', 'enforcement', 'is_active')


@admin.register(ProhibitedItemDetection)
class ProhibitedItemDetectionAdmin(admin.ModelAdmin):
    list_display = ('rule', 'listing_id', 'matched_kind',
                    'action_taken', 'detected_at')
    list_filter = ('matched_kind',)


@admin.register(BrandKeywordWatch)
class BrandKeywordWatchAdmin(admin.ModelAdmin):
    list_display = ('brand', 'auto_remove_threshold', 'is_active')


@admin.register(CounterfeitSignal)
class CounterfeitSignalAdmin(admin.ModelAdmin):
    list_display = ('listing_id', 'brand', 'kind',
                    'confidence', 'detected_at')
    list_filter = ('kind',)


@admin.register(CounterfeitCase)
class CounterfeitCaseAdmin(admin.ModelAdmin):
    list_display = ('listing_id', 'seller', 'brand',
                    'composite_confidence', 'status',
                    'repeat_offence_count', 'decided_at')
    list_filter = ('status',)


@admin.register(CsamHashEntry)
class CsamHashEntryAdmin(admin.ModelAdmin):
    list_display = ('hash_value', 'list_source', 'list_version', 'added_at')
    list_filter = ('list_source',)


@admin.register(CsamIncident)
class CsamIncidentAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'surface', 'detected_at',
                    'reported_at')
    list_filter = ('status',)
    readonly_fields = ('upload_reference', 'matched_hash',
                       'uploader_user')


@admin.register(HateSpeechDetection)
class HateSpeechDetectionAdmin(admin.ModelAdmin):
    list_display = ('surface', 'surface_id', 'author',
                    'kind', 'confidence', 'detected_at')
    list_filter = ('kind', 'surface')


@admin.register(HateSpeechEnforcement)
class HateSpeechEnforcementAdmin(admin.ModelAdmin):
    list_display = ('detection', 'action', 'suspension_days',
                    'actor_kind', 'enforced_at')


@admin.register(IpRightsHolder)
class IpRightsHolderAdmin(admin.ModelAdmin):
    list_display = ('legal_name', 'country', 'contact_email',
                    'verified', 'verified_at')
    list_filter = ('verified', 'country')


@admin.register(IpComplaint)
class IpComplaintAdmin(admin.ModelAdmin):
    list_display = ('rights_holder', 'listing_id', 'kind',
                    'status', 'filed_at', 'decided_at')
    list_filter = ('status', 'kind')


@admin.register(IpComplaintResponse)
class IpComplaintResponseAdmin(admin.ModelAdmin):
    list_display = ('complaint', 'response_kind', 'submitted_at')


@admin.register(DmcaNotice)
class DmcaNoticeAdmin(admin.ModelAdmin):
    list_display = ('notice_number', 'submitter_name',
                    'validation_status', 'filed_at',
                    'listing_removed_at')
    list_filter = ('validation_status',)


@admin.register(DmcaCounterNotice)
class DmcaCounterNoticeAdmin(admin.ModelAdmin):
    list_display = ('notice', 'submitter_name', 'restore_due_at',
                    'restored_at')


@admin.register(PriceGougingFlag)
class PriceGougingFlagAdmin(admin.ModelAdmin):
    list_display = ('listing_id', 'baseline_price', 'new_price',
                    'spike_pct', 'is_emergency_period',
                    'action_taken', 'detected_at')
    list_filter = ('is_emergency_period', 'action_taken')


@admin.register(ImpersonationCheck)
class ImpersonationCheckAdmin(admin.ModelAdmin):
    list_display = ('suspect_user', 'suspect_store_name',
                    'legitimate_brand', 'similarity_score', 'status')
    list_filter = ('status',)


@admin.register(BanEvasionSignal)
class BanEvasionSignalAdmin(admin.ModelAdmin):
    list_display = ('new_user', 'banned_user', 'match_kind',
                    'match_score', 'auto_suspended', 'detected_at')
    list_filter = ('match_kind', 'auto_suspended')


@admin.register(CoordinatedBuyingRing)
class CoordinatedBuyingRingAdmin(admin.ModelAdmin):
    list_display = ('seller', 'suspicious_order_count',
                    'severity', 'status', 'detected_at')
    list_filter = ('status',)


@admin.register(ManipulationFlag)
class ManipulationFlagAdmin(admin.ModelAdmin):
    list_display = ('listing_id', 'kind', 'detected_at')
    list_filter = ('kind',)


@admin.register(AgeGatedCategory)
class AgeGatedCategoryAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'min_age', 'requires_id', 'is_active')
    list_filter = ('requires_id', 'is_active')


@admin.register(AgeGateChallenge)
class AgeGateChallengeAdmin(admin.ModelAdmin):
    list_display = ('user', 'category_id', 'passed',
                    'verification_method', 'challenged_at')
    list_filter = ('passed', 'verification_method')


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ('blocker', 'blocked', 'blocker_kind',
                    'reason', 'created_at')
    list_filter = ('blocker_kind',)


@admin.register(UserReport)
class UserReportAdmin(admin.ModelAdmin):
    list_display = ('reporter', 'subject_user', 'kind',
                    'severity', 'triage_class', 'status', 'reported_at')
    list_filter = ('kind', 'triage_class', 'status')


@admin.register(SellerBlacklistEntry)
class SellerBlacklistEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'scope', 'reason_codes',
                    'industry_shared', 'expiry', 'created_at')
    list_filter = ('scope', 'industry_shared')


@admin.register(BlacklistCheck)
class BlacklistCheckAdmin(admin.ModelAdmin):
    list_display = ('subject_kind', 'subject_user',
                    'match_score', 'outcome', 'checked_at')
    list_filter = ('subject_kind', 'outcome')


@admin.register(ReviewAuthenticitySignal)
class ReviewAuthenticitySignalAdmin(admin.ModelAdmin):
    list_display = ('review_id', 'reviewer', 'signal_kind',
                    'confidence', 'detected_at')
    list_filter = ('signal_kind',)


@admin.register(ReviewFraudRing)
class ReviewFraudRingAdmin(admin.ModelAdmin):
    list_display = ('id', 'signal_count', 'confidence',
                    'status', 'detected_at')
    list_filter = ('status',)


@admin.register(AccountTakeoverCase)
class AccountTakeoverCaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'risk_score', 'status',
                    'quarantine_action', 'detected_at')
    list_filter = ('status',)


@admin.register(EnhancedDueDiligenceReview)
class EnhancedDueDiligenceReviewAdmin(admin.ModelAdmin):
    list_display = ('seller', 'triggered_by', 'risk_score',
                    'status', 'decided_at')
    list_filter = ('status', 'triggered_by')


@admin.register(SerialDisputerSignal)
class SerialDisputerSignalAdmin(admin.ModelAdmin):
    list_display = ('user', 'dispute_count',
                    'successful_refund_count', 'severity',
                    'detected_at')


@admin.register(RefundFarmingCase)
class RefundFarmingCaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_refund_amount',
                    'confidence', 'status', 'detected_at')
    list_filter = ('status',)


@admin.register(BuyerFraudRing)
class BuyerFraudRingAdmin(admin.ModelAdmin):
    list_display = ('cluster_signature', 'fraud_pattern',
                    'member_count', 'total_loss_estimate',
                    'status', 'detected_at')
    list_filter = ('fraud_pattern', 'status')


@admin.register(BuyerFraudRingMember)
class BuyerFraudRingMemberAdmin(admin.ModelAdmin):
    list_display = ('ring', 'user', 'role_in_ring', 'confidence')


@admin.register(ProductRecall)
class ProductRecallAdmin(admin.ModelAdmin):
    list_display = ('recall_reference', 'product_id', 'severity',
                    'recall_source', 'status', 'announced_at')
    list_filter = ('severity', 'status')


@admin.register(RecallNotification)
class RecallNotificationAdmin(admin.ModelAdmin):
    list_display = ('recall', 'affected_user', 'order_id',
                    'channel', 'sent_at', 'refund_issued')


@admin.register(ExportControlListing)
class ExportControlListingAdmin(admin.ModelAdmin):
    list_display = ('listing_id', 'destination_country',
                    'outcome', 'last_checked_at')
    list_filter = ('outcome', 'destination_country')


@admin.register(BuyerTrustScore)
class BuyerTrustScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'score', 'band', 'last_computed_at')
    list_filter = ('band',)


@admin.register(AppealRequest)
class AppealRequestAdmin(admin.ModelAdmin):
    list_display = ('appellant', 'decision_kind', 'status',
                    'submitted_at', 'resolved_at')
    list_filter = ('decision_kind', 'status')


@admin.register(AppealDecision)
class AppealDecisionAdmin(admin.ModelAdmin):
    list_display = ('appeal', 'decision', 'reviewer', 'decided_at')


@admin.register(LawEnforcementRequest)
class LawEnforcementRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'agency', 'jurisdiction',
                    'request_kind', 'status', 'deadline_at',
                    'user_notified')
    list_filter = ('status', 'request_kind', 'user_notified')


@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = ('subject_user', 'started_at',
                    'expected_release_at', 'released_at')


@admin.register(TrustSafetyKpiSnapshot)
class TrustSafetyKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'prohibited_detections',
                    'counterfeit_cases_opened', 'csam_incidents',
                    'ip_complaints_filed', 'le_requests_received',
                    'auto_action_rate')


@admin.register(TrustSafetyEvent)
class TrustSafetyEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'subject_kind', 'subject_id',
                    'user', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'subject_kind', 'subject_id',
                       'user', 'actor', 'payload', 'created_at')
