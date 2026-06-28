"""
Trust & Safety — data model
===========================

Implements AliExpress_Trust_Safety_Additional.docx CH1–CH24 where
existing apps don't already own the schema. We DO NOT duplicate:

  - apps.trust.SellerTrustScore / TrustScoreHistory / TrustEvent
  - apps.fraud_engine.DeviceFingerprint / VelocityRule / FraudDecision
  - apps.security.SecurityAuditLog / IPBan / BannedKeyword
  - apps.payment_ops.SanctionsScreen
  - apps.cs_ops.TrustSafetyReport

New tables here cover the gap:

  CH1   TsModel, TsDecision               — ML pipeline registry + decisions
  CH2   ProhibitedItemRule, ProhibitedItemDetection
  CH3   CounterfeitSignal, CounterfeitCase, BrandKeywordWatch
  CH4   CsamHashEntry, CsamIncident       — immediate-removal protocol
  CH5   HateSpeechDetection, HateSpeechEnforcement
  CH6   IpRightsHolder, IpComplaint, IpComplaintResponse
  CH7   DmcaNotice, DmcaCounterNotice
  CH8   PriceGougingFlag                  — emergency price spike
  CH9   ImpersonationCheck, BanEvasionSignal
  CH10  CoordinatedBuyingRing, ManipulationFlag
  CH11  AgeGatedCategory, AgeGateChallenge
  CH12  UserBlock, UserReport             — buyer↔seller block & report
  CH13  SellerBlacklistEntry, BlacklistCheck
  CH14  ReviewAuthenticitySignal, ReviewFraudRing
  CH15  AccountTakeoverCase
  CH16  EnhancedDueDiligenceReview
  CH17  SerialDisputerSignal, RefundFarmingCase
  CH18  BuyerFraudRing, BuyerFraudRingMember
  CH19  ProductRecall, RecallNotification
  CH20  ExportControlListing
  CH21  BuyerTrustScore                    — seller trust lives in apps.trust
  CH22  AppealRequest, AppealDecision
  CH23  LawEnforcementRequest, LegalHold
  CH24  TrustSafetyKpiSnapshot
  Audit TrustSafetyEvent
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────
# CH1 — ML pipeline + decisions
# ─────────────────────────────────────────────────────────────────

ML_MODEL_KIND_CHOICES = (
    ('text_classifier',   'Text classifier'),
    ('image_classifier',  'Image classifier'),
    ('hash_matcher',      'Hash matcher'),
    ('embedding_similarity','Embedding similarity'),
    ('rule_engine',       'Rule engine'),
    ('graph_analytics',   'Graph analytics'),
    ('anomaly_detector',  'Anomaly detector'),
)


class TsModel(models.Model):
    """Registry of every detection model deployed. Versioned so we
    can A/B + roll back. Decisions reference the model that fired."""

    code = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=ML_MODEL_KIND_CHOICES)
    version = models.CharField(max_length=20)
    surfaces = models.JSONField(
        default=list, blank=True,
        help_text='Surfaces this model scans: listing/review/message/profile/order',
    )
    confidence_threshold = models.FloatField(default=0.85)
    auto_action_threshold = models.FloatField(
        default=0.95,
        help_text='Decisions above this fire automatic enforcement; below '
                  'goes to a human reviewer.',
    )
    is_active = models.BooleanField(default=True)
    deployed_at = models.DateTimeField(auto_now_add=True)


TS_DECISION_OUTCOME_CHOICES = (
    ('clean',          'Clean'),
    ('flag_for_review','Flag for review'),
    ('auto_remove',    'Auto-removed'),
    ('auto_warn',      'Auto-warned'),
    ('auto_ban',       'Auto-ban'),
    ('escalate_human', 'Escalate to human reviewer'),
    ('escalate_law',   'Escalate to law enforcement'),
)


class TsDecision(models.Model):
    """One row per model invocation. The append-only decision log is
    what we replay when training new models / auditing biases."""

    id = models.BigAutoField(primary_key=True)
    model = models.ForeignKey(TsModel, on_delete=models.PROTECT, related_name='decisions')
    surface = models.CharField(
        max_length=24, db_index=True,
        help_text='listing|review|message|profile|order',
    )
    subject_kind = models.CharField(
        max_length=24,
        choices=(('listing', 'Listing'), ('review', 'Review'),
                 ('message', 'Message'), ('profile', 'Profile'),
                 ('order', 'Order'), ('image', 'Image'),
                 ('comment', 'Comment')),
    )
    subject_id = models.CharField(max_length=64, db_index=True)
    confidence = models.FloatField()
    outcome = models.CharField(max_length=20, choices=TS_DECISION_OUTCOME_CHOICES)
    features = models.JSONField(default=dict, blank=True)
    matched_rules = models.JSONField(default=list, blank=True)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ts_decisions_reviewed',
    )
    reviewer_override = models.CharField(max_length=20, blank=True, default='')
    decided_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['subject_kind', 'subject_id', '-decided_at']),
            models.Index(fields=['outcome', '-decided_at']),
        ]


# ─────────────────────────────────────────────────────────────────
# CH2 — Prohibited items
# ─────────────────────────────────────────────────────────────────

PROHIBITED_CATEGORY_CHOICES = (
    ('weapons',             'Weapons / firearms'),
    ('drugs',               'Drugs / narcotics'),
    ('counterfeit_money',   'Counterfeit currency'),
    ('hazardous',           'Hazardous materials'),
    ('endangered_wildlife', 'Endangered wildlife'),
    ('human_remains',       'Human remains'),
    ('stolen_goods',        'Stolen goods'),
    ('csam',                'Child sexual abuse material'),
    ('hate_symbols',        'Hate symbols'),
    ('regulated_medical',   'Regulated medical devices'),
    ('tobacco',             'Tobacco / vape'),
    ('alcohol_unregistered','Unregistered alcohol'),
    ('financial_instruments','Financial instruments'),
    ('political_regulated', 'Politically regulated items'),
    ('other_prohibited',    'Other prohibited'),
)


class ProhibitedItemRule(models.Model):
    """Keyword / image-hash / category combinations that trigger
    prohibited-item flags."""

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=40, unique=True)
    category = models.CharField(max_length=24, choices=PROHIBITED_CATEGORY_CHOICES, db_index=True)
    keywords = models.JSONField(default=list, blank=True)
    image_hash_prefixes = models.JSONField(default=list, blank=True)
    country_scope = models.JSONField(
        default=list, blank=True,
        help_text='Empty list = global. Use ISO codes to scope.',
    )
    enforcement = models.CharField(
        max_length=24, default='auto_remove',
        choices=(('block_at_listing', 'Block at listing'),
                 ('auto_remove', 'Auto-remove'),
                 ('flag_for_review', 'Flag for review'),
                 ('warn_seller', 'Warn seller')),
    )
    severity = models.PositiveSmallIntegerField(default=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProhibitedItemDetection(models.Model):
    id = models.BigAutoField(primary_key=True)
    rule = models.ForeignKey(ProhibitedItemRule, on_delete=models.PROTECT, related_name='detections')
    listing_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prohibited_detections',
    )
    matched_kind = models.CharField(
        max_length=16,
        choices=(('text', 'Text'), ('image', 'Image'),
                 ('both', 'Both'), ('manual', 'Manual')),
    )
    matched_terms = models.JSONField(default=list, blank=True)
    matched_image_hash = models.CharField(max_length=64, blank=True, default='')
    action_taken = models.CharField(max_length=24, blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH3 — Counterfeit
# ─────────────────────────────────────────────────────────────────

class BrandKeywordWatch(models.Model):
    """Brand owners pre-register protected keywords. Listings using
    these strings get screened — sellers without authorisation are
    flagged."""

    id = models.BigAutoField(primary_key=True)
    brand = models.CharField(max_length=120, db_index=True)
    protected_keywords = models.JSONField(default=list)
    rights_holder_id = models.CharField(max_length=64, blank=True, default='')
    auto_remove_threshold = models.FloatField(default=0.92)
    is_active = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)


COUNTERFEIT_SIGNAL_KIND_CHOICES = (
    ('keyword_abuse',     'Brand keyword abuse'),
    ('fake_logo',         'Fake logo visual match'),
    ('price_outlier',     'Price too low vs MSRP'),
    ('seller_not_authorised','Seller not authorised reseller'),
    ('clone_listing',     'Clone listing pattern'),
    ('hologram_missing',  'Hologram / serial missing'),
)


class CounterfeitSignal(models.Model):
    """One row per detected signal — a case may have many signals."""

    id = models.BigAutoField(primary_key=True)
    listing_id = models.CharField(max_length=64, db_index=True)
    brand = models.CharField(max_length=120, db_index=True)
    kind = models.CharField(max_length=24, choices=COUNTERFEIT_SIGNAL_KIND_CHOICES)
    confidence = models.FloatField()
    evidence = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)


COUNTERFEIT_CASE_STATUS_CHOICES = (
    ('open',          'Open'),
    ('seller_warned', 'Seller warned'),
    ('listing_removed','Listing removed'),
    ('seller_banned', 'Seller banned'),
    ('dismissed',     'Dismissed — false positive'),
)


class CounterfeitCase(models.Model):
    """Result of the CH3.3 decision tree — aggregates signals on a
    listing and runs through the enforcement ladder."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing_id = models.CharField(max_length=64, unique=True, db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='counterfeit_cases',
    )
    brand = models.CharField(max_length=120, blank=True, default='')
    signal_count = models.PositiveSmallIntegerField(default=0)
    composite_confidence = models.FloatField(default=0.0)
    status = models.CharField(
        max_length=20, choices=COUNTERFEIT_CASE_STATUS_CHOICES, default='open',
    )
    repeat_offence_count = models.PositiveSmallIntegerField(default=0)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH4 — CSAM (child safety) — IMMEDIATE removal protocol
# ─────────────────────────────────────────────────────────────────

class CsamHashEntry(models.Model):
    """PhotoDNA / NCMEC / IWF hash list. Any image whose hash matches
    here triggers the CH4.2 immediate-response protocol."""

    hash_value = models.CharField(max_length=64, primary_key=True)
    list_source = models.CharField(
        max_length=20,
        choices=(('ncmec', 'NCMEC'), ('iwf', 'IWF'),
                 ('inhope', 'INHOPE'), ('photodna', 'PhotoDNA'),
                 ('internal', 'Internal')),
    )
    list_version = models.CharField(max_length=20)
    added_at = models.DateTimeField(auto_now_add=True)


CSAM_INCIDENT_STATUS_CHOICES = (
    ('detected',          'Detected — content quarantined'),
    ('reported_ncmec',    'Reported to NCMEC'),
    ('seller_banned',     'Seller banned'),
    ('le_notified',       'Law enforcement notified'),
    ('closed',            'Closed'),
)


class CsamIncident(models.Model):
    """Created when a CSAM hash hit fires. PII is deliberately minimal
    — only the upload reference + reporter."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload_reference = models.CharField(
        max_length=120, db_index=True,
        help_text='Storage key of the matched upload (quarantined bucket).',
    )
    matched_hash = models.CharField(max_length=64, db_index=True)
    uploader_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csam_incidents',
    )
    surface = models.CharField(max_length=24)
    surface_id = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=20, choices=CSAM_INCIDENT_STATUS_CHOICES, default='detected')
    ncmec_report_id = models.CharField(max_length=120, blank=True, default='')
    le_request_id = models.CharField(max_length=120, blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True)
    reported_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH5 — Hate speech & extremism
# ─────────────────────────────────────────────────────────────────

HATE_KIND_CHOICES = (
    ('hate_race',           'Race / ethnicity'),
    ('hate_religion',       'Religion'),
    ('hate_sexual_orient',  'Sexual orientation'),
    ('hate_gender',         'Gender identity'),
    ('hate_disability',     'Disability'),
    ('extremism_violent',   'Violent extremism'),
    ('threat_specific',     'Specific threat'),
    ('harassment',          'Harassment'),
)


class HateSpeechDetection(models.Model):
    id = models.BigAutoField(primary_key=True)
    surface = models.CharField(max_length=24, db_index=True)
    surface_id = models.CharField(max_length=64, db_index=True)
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hate_detections_authored',
    )
    text_excerpt = models.TextField()
    kind = models.CharField(max_length=24, choices=HATE_KIND_CHOICES)
    confidence = models.FloatField()
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)


HATE_ENFORCEMENT_KIND_CHOICES = (
    ('content_removed', 'Content removed'),
    ('user_warned',     'User warned'),
    ('user_suspended',  'User suspended'),
    ('user_banned',     'User banned'),
    ('content_kept',    'Kept — false positive'),
)


class HateSpeechEnforcement(models.Model):
    id = models.BigAutoField(primary_key=True)
    detection = models.OneToOneField(HateSpeechDetection, on_delete=models.CASCADE, related_name='enforcement')
    action = models.CharField(max_length=20, choices=HATE_ENFORCEMENT_KIND_CHOICES)
    suspension_days = models.PositiveSmallIntegerField(default=0)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hate_enforcements_taken',
    )
    actor_kind = models.CharField(
        max_length=12, default='auto',
        choices=(('auto', 'Auto'), ('reviewer', 'Reviewer')),
    )
    enforced_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH6 — IP complaints
# ─────────────────────────────────────────────────────────────────

class IpRightsHolder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legal_name = models.CharField(max_length=200)
    country = models.CharField(max_length=2)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    verified = models.BooleanField(default=False)
    verification_doc_key = models.CharField(max_length=255, blank=True, default='')
    protected_brands = models.JSONField(default=list, blank=True)
    protected_trademarks = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)


IP_COMPLAINT_KIND_CHOICES = (
    ('trademark',     'Trademark infringement'),
    ('copyright',     'Copyright infringement'),
    ('patent',        'Patent infringement'),
    ('design_right',  'Design right'),
    ('passing_off',   'Passing off'),
)

IP_COMPLAINT_STATUS_CHOICES = (
    ('filed',            'Filed'),
    ('seller_notified',  'Seller notified — awaiting response'),
    ('seller_responded', 'Seller responded'),
    ('upheld_removed',   'Upheld — listing removed'),
    ('rejected',         'Rejected — listing restored'),
    ('partial_upheld',   'Partially upheld'),
    ('counter_notified', 'Counter-notified — sent to complainant'),
    ('expired',          'Expired'),
)


class IpComplaint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rights_holder = models.ForeignKey(IpRightsHolder, on_delete=models.PROTECT, related_name='complaints')
    listing_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ip_complaints_received',
    )
    kind = models.CharField(max_length=16, choices=IP_COMPLAINT_KIND_CHOICES)
    description = models.TextField()
    supporting_evidence = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=IP_COMPLAINT_STATUS_CHOICES, default='filed')
    seller_response_due_at = models.DateTimeField()
    decision_due_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True, default='')
    filed_at = models.DateTimeField(auto_now_add=True)


class IpComplaintResponse(models.Model):
    """Seller's response. Either accepts, counter-notifies, or
    requests review."""

    id = models.BigAutoField(primary_key=True)
    complaint = models.ForeignKey(IpComplaint, on_delete=models.CASCADE, related_name='responses')
    response_kind = models.CharField(
        max_length=20,
        choices=(('accept_remove', 'Accept — removed'),
                 ('counter_notice', 'Counter-notice'),
                 ('authorised_reseller', 'Authorised reseller proof'),
                 ('fair_use', 'Fair use argument'),
                 ('other', 'Other')),
    )
    response_text = models.TextField()
    evidence_keys = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH7 — DMCA
# ─────────────────────────────────────────────────────────────────

DMCA_VALIDATION_STATUS_CHOICES = (
    ('pending',          'Pending validation'),
    ('valid',            'Valid'),
    ('invalid',          'Invalid — missing elements'),
    ('processed',        'Processed — content removed'),
    ('counter_notified', 'Counter-notice filed'),
    ('restored',         'Content restored after counter-notice'),
    ('expired',          'Expired'),
)


class DmcaNotice(models.Model):
    """A formal DMCA takedown notice. Validation checks the 6 required
    elements per US 17 USC 512(c)(3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notice_number = models.CharField(max_length=20, unique=True, db_index=True)
    submitter_name = models.CharField(max_length=200)
    submitter_email = models.EmailField()
    submitter_phone = models.CharField(max_length=30, blank=True, default='')
    works_described = models.TextField()
    allegedly_infringing_urls = models.JSONField(default=list)
    listing_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    good_faith_statement = models.BooleanField(default=False)
    accuracy_statement = models.BooleanField(default=False)
    authorised_signature = models.CharField(max_length=200)
    validation_status = models.CharField(max_length=20, choices=DMCA_VALIDATION_STATUS_CHOICES, default='pending')
    validation_failures = models.JSONField(default=list, blank=True)
    listing_removed_at = models.DateTimeField(null=True, blank=True)
    filed_at = models.DateTimeField(auto_now_add=True)


class DmcaCounterNotice(models.Model):
    id = models.BigAutoField(primary_key=True)
    notice = models.OneToOneField(DmcaNotice, on_delete=models.CASCADE, related_name='counter_notice')
    submitter_name = models.CharField(max_length=200)
    submitter_email = models.EmailField()
    perjury_statement = models.BooleanField(default=False)
    jurisdiction_statement = models.BooleanField(default=False)
    counter_signature = models.CharField(max_length=200)
    restore_due_at = models.DateTimeField(
        help_text='Per DMCA 10-14 business day window.',
    )
    restored_at = models.DateTimeField(null=True, blank=True)
    filed_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH8 — Price gouging
# ─────────────────────────────────────────────────────────────────

class PriceGougingFlag(models.Model):
    id = models.BigAutoField(primary_key=True)
    listing_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='price_gouging_flags',
    )
    baseline_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    spike_pct = models.DecimalField(max_digits=8, decimal_places=2)
    is_emergency_period = models.BooleanField(default=False)
    is_coordinated = models.BooleanField(
        default=False,
        help_text='True if part of a multi-seller manipulation cluster.',
    )
    action_taken = models.CharField(
        max_length=20, default='flagged',
        choices=(('flagged', 'Flagged'),
                 ('price_reverted', 'Price reverted'),
                 ('listing_suspended', 'Listing suspended'),
                 ('seller_warned', 'Seller warned'),
                 ('dismissed', 'Dismissed')),
    )
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH9 — Impersonation + ban evasion
# ─────────────────────────────────────────────────────────────────

IMPERSONATION_STATUS_CHOICES = (
    ('pending',  'Pending review'),
    ('cleared',  'Cleared'),
    ('warned',   'Seller warned'),
    ('suspended','Suspended'),
    ('banned',   'Banned'),
)


class ImpersonationCheck(models.Model):
    id = models.BigAutoField(primary_key=True)
    suspect_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='impersonation_checks')
    suspect_store_name = models.CharField(max_length=200)
    legitimate_brand = models.CharField(max_length=120, blank=True, default='')
    similarity_score = models.FloatField()
    matched_brand_keywords = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=12, choices=IMPERSONATION_STATUS_CHOICES, default='pending')
    detected_at = models.DateTimeField(auto_now_add=True)


class BanEvasionSignal(models.Model):
    """Heuristic match — same device fingerprint / bank account /
    address re-appearing after a ban."""

    id = models.BigAutoField(primary_key=True)
    new_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ban_evasion_signals')
    banned_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='banned_user_evasion_signals',
    )
    match_kind = models.CharField(
        max_length=20,
        choices=(('device', 'Device'), ('ip_subnet', 'IP subnet'),
                 ('bank_account', 'Bank account'),
                 ('shipping_addr', 'Shipping address'),
                 ('phone_number', 'Phone number'),
                 ('email_pattern', 'Email pattern')),
    )
    match_score = models.FloatField()
    auto_suspended = models.BooleanField(default=False)
    reviewed = models.BooleanField(default=False)
    detected_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH10 — Coordinated buying / marketplace manipulation
# ─────────────────────────────────────────────────────────────────

class CoordinatedBuyingRing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coordinated_buying_rings')
    member_user_ids = models.JSONField(default=list, blank=True)
    suspicious_order_count = models.PositiveIntegerField(default=0)
    refund_after_review_count = models.PositiveIntegerField(default=0)
    detection_window_days = models.PositiveSmallIntegerField(default=14)
    severity = models.PositiveSmallIntegerField(default=50)
    status = models.CharField(
        max_length=16, default='open',
        choices=(('open', 'Open'), ('confirmed', 'Confirmed'),
                 ('dismissed', 'Dismissed'),
                 ('action_taken', 'Action taken')),
    )
    detected_at = models.DateTimeField(auto_now_add=True)


class ManipulationFlag(models.Model):
    id = models.BigAutoField(primary_key=True)
    listing_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='manipulation_flags',
    )
    kind = models.CharField(
        max_length=24,
        choices=(('coordinated_buy', 'Coordinated buying'),
                 ('shill_review',    'Shill reviews'),
                 ('wash_trade',      'Wash trade'),
                 ('rank_manipulation','Search rank manipulation')),
    )
    evidence = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH11 — Age gates
# ─────────────────────────────────────────────────────────────────

class AgeGatedCategory(models.Model):
    category_id = models.CharField(max_length=64, primary_key=True)
    min_age = models.PositiveSmallIntegerField(default=18)
    requires_id = models.BooleanField(default=False)
    country_scope = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)


class AgeGateChallenge(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='age_gate_challenges')
    category_id = models.CharField(max_length=64)
    claimed_dob = models.DateField()
    passed = models.BooleanField()
    verification_method = models.CharField(
        max_length=20, default='self_declared',
        choices=(('self_declared', 'Self-declared'),
                 ('id_uploaded', 'ID uploaded'),
                 ('credit_card', 'Credit card'),
                 ('third_party', 'Third-party verification')),
    )
    challenged_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH12 — User block + report
# ─────────────────────────────────────────────────────────────────

class UserBlock(models.Model):
    """Per-pair block. Buyer blocks seller (or vice-versa) hides all
    interaction between them."""

    id = models.BigAutoField(primary_key=True)
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_created')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_received')
    reason = models.CharField(max_length=120, blank=True, default='')
    blocker_kind = models.CharField(
        max_length=12,
        choices=(('buyer', 'Buyer blocks seller'),
                 ('seller', 'Seller blocks buyer'),
                 ('mutual', 'Mutual')),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('blocker', 'blocked')]


USER_REPORT_KIND_CHOICES = (
    ('seller_misconduct', 'Seller misconduct'),
    ('buyer_misconduct',  'Buyer misconduct'),
    ('listing_issue',     'Listing issue'),
    ('review_issue',      'Review issue'),
    ('chat_abuse',        'Chat abuse'),
    ('safety_concern',    'Safety concern'),
    ('other',             'Other'),
)

USER_REPORT_TRIAGE_CHOICES = (
    ('p1', 'P1 — Immediate (T&S team)'),
    ('p2', 'P2 — Same day (Trust Ops)'),
    ('p3', 'P3 — 72h (Tier 2)'),
    ('p4', 'P4 — Best effort (Tier 1)'),
)


class UserReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_reports_made')
    subject_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='user_reports_against',
    )
    subject_listing_id = models.CharField(max_length=64, blank=True, default='')
    subject_review_id = models.CharField(max_length=64, blank=True, default='')
    kind = models.CharField(max_length=20, choices=USER_REPORT_KIND_CHOICES)
    severity = models.PositiveSmallIntegerField(default=5)
    triage_class = models.CharField(max_length=2, choices=USER_REPORT_TRIAGE_CHOICES, default='p3')
    description = models.TextField()
    evidence = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16, default='open',
        choices=(('open', 'Open'), ('triaged', 'Triaged'),
                 ('investigating', 'Investigating'),
                 ('actioned', 'Actioned'),
                 ('dismissed', 'Dismissed')),
    )
    actioned_outcome = models.CharField(max_length=120, blank=True, default='')
    reported_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH13 — Seller blacklist
# ─────────────────────────────────────────────────────────────────

class SellerBlacklistEntry(models.Model):
    """Permanent global / regional blacklist. Looked up at signup
    and at every payout."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legal_name_hash = models.CharField(max_length=64, db_index=True)
    business_reg_hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    email_hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    phone_hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    ip_subnet = models.CharField(max_length=64, blank=True, default='')
    device_fingerprint = models.CharField(max_length=64, blank=True, default='')
    scope = models.CharField(
        max_length=12, default='global',
        choices=(('global', 'Global'), ('regional', 'Regional')),
    )
    country_scope = models.JSONField(default=list, blank=True)
    reason_codes = models.JSONField(default=list, blank=True)
    expiry = models.DateField(
        null=True, blank=True,
        help_text='NULL = permanent. Set a date for time-bound bans.',
    )
    industry_shared = models.BooleanField(
        default=False,
        help_text='If True, this entry is contributed to the industry '
                  'blacklist consortium.',
    )
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='blacklist_entries_added',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class BlacklistCheck(models.Model):
    """Append-only check log. Every signup / payout writes one row."""

    id = models.BigAutoField(primary_key=True)
    subject_kind = models.CharField(
        max_length=12,
        choices=(('signup', 'Signup'),
                 ('payout', 'Payout'),
                 ('reapply', 'Reapply')),
    )
    subject_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='blacklist_checks',
    )
    matched_entry = models.ForeignKey(
        SellerBlacklistEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checks',
    )
    match_score = models.FloatField(default=0.0)
    outcome = models.CharField(
        max_length=12, default='allowed',
        choices=(('allowed', 'Allowed'),
                 ('blocked', 'Blocked'),
                 ('review', 'Manual review')),
    )
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH14 — Review fraud
# ─────────────────────────────────────────────────────────────────

REVIEW_FRAUD_SIGNAL_KIND_CHOICES = (
    ('verified_purchase_no','Not a verified purchase'),
    ('reviewer_cluster',    'Reviewer cluster'),
    ('rapid_5star_burst',   '5-star burst'),
    ('text_template_match', 'Templated review text'),
    ('translated_template', 'Same translated template'),
    ('refund_for_review',   'Refund-for-review pattern'),
    ('incentivised',        'Incentivised review'),
)


class ReviewAuthenticitySignal(models.Model):
    id = models.BigAutoField(primary_key=True)
    review_id = models.CharField(max_length=64, db_index=True)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='review_signals_emitted',
    )
    listing_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    signal_kind = models.CharField(max_length=24, choices=REVIEW_FRAUD_SIGNAL_KIND_CHOICES)
    confidence = models.FloatField()
    evidence = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)


class ReviewFraudRing(models.Model):
    """Cluster of accounts identified as a review farm."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member_user_ids = models.JSONField(default=list)
    reviewed_listings = models.JSONField(default=list, blank=True)
    signal_count = models.PositiveIntegerField(default=0)
    confidence = models.FloatField()
    status = models.CharField(
        max_length=16, default='open',
        choices=(('open', 'Open'),
                 ('confirmed', 'Confirmed — reviews removed'),
                 ('dismissed', 'Dismissed')),
    )
    detected_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — Account takeover
# ─────────────────────────────────────────────────────────────────

ATO_STATUS_CHOICES = (
    ('detected',     'Detected'),
    ('quarantined',  'Account quarantined'),
    ('recovered',    'Recovered by owner'),
    ('false_positive','False positive'),
    ('confirmed',    'Confirmed ATO'),
)


class AccountTakeoverCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ato_cases')
    detection_signals = models.JSONField(default=list, blank=True)
    risk_score = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=ATO_STATUS_CHOICES, default='detected')
    quarantine_action = models.CharField(
        max_length=24, blank=True, default='',
        choices=(('logout_all', 'Logout all sessions'),
                 ('block_payouts', 'Block payouts'),
                 ('require_2fa', 'Require 2FA'),
                 ('email_lock', 'Lock email changes')),
    )
    recovery_method = models.CharField(max_length=24, blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH16 — Enhanced due diligence
# ─────────────────────────────────────────────────────────────────

class EnhancedDueDiligenceReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='edd_reviews')
    triggered_by = models.CharField(
        max_length=24,
        choices=(('high_risk_country', 'High-risk country'),
                 ('high_value_category', 'High-value category'),
                 ('post_signup_review', 'Post-signup review'),
                 ('alert_triggered', 'AML alert triggered'),
                 ('manual_request', 'Manual request')),
    )
    risk_score = models.PositiveSmallIntegerField(default=50)
    required_docs = models.JSONField(default=list, blank=True)
    documents_received = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16, default='pending',
        choices=(('pending', 'Pending'),
                 ('docs_received', 'Docs received'),
                 ('approved', 'Approved'),
                 ('rejected', 'Rejected — banned')),
    )
    decision_notes = models.TextField(blank=True, default='')
    investigator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='edd_reviews_handled',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH17 — Serial disputer + refund farmer
# ─────────────────────────────────────────────────────────────────

class SerialDisputerSignal(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='serial_disputer_signals')
    detection_window_days = models.PositiveSmallIntegerField(default=90)
    dispute_count = models.PositiveIntegerField()
    successful_refund_count = models.PositiveIntegerField()
    refund_total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    severity = models.PositiveSmallIntegerField(default=50)
    detected_at = models.DateTimeField(auto_now_add=True)


REFUND_FARMING_STATUS_CHOICES = (
    ('open',                 'Open'),
    ('confirmed',            'Confirmed'),
    ('account_suspended',    'Account suspended'),
    ('refunds_clawed_back',  'Refunds clawed back'),
    ('false_positive',       'False positive'),
)


class RefundFarmingCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refund_farming_cases')
    signals = models.JSONField(default=list, blank=True)
    total_refund_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    confidence = models.FloatField()
    status = models.CharField(max_length=20, choices=REFUND_FARMING_STATUS_CHOICES, default='open')
    action_notes = models.TextField(blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True)
    actioned_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — Buyer fraud rings
# ─────────────────────────────────────────────────────────────────

class BuyerFraudRing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cluster_signature = models.CharField(max_length=64, unique=True, db_index=True)
    fraud_pattern = models.CharField(
        max_length=32,
        choices=(('triangulation', 'Triangulation'),
                 ('chargeback_ring', 'Chargeback ring'),
                 ('stolen_card_test', 'Stolen card testing'),
                 ('refund_ring', 'Refund ring'),
                 ('account_farm', 'Account farm')),
    )
    member_count = models.PositiveSmallIntegerField(default=0)
    total_loss_estimate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    confidence = models.FloatField()
    status = models.CharField(
        max_length=16, default='open',
        choices=(('open', 'Open'),
                 ('confirmed', 'Confirmed'),
                 ('shutdown', 'Shutdown — accounts banned'),
                 ('dismissed', 'Dismissed')),
    )
    investigator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='buyer_fraud_rings_investigating',
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)


class BuyerFraudRingMember(models.Model):
    id = models.BigAutoField(primary_key=True)
    ring = models.ForeignKey(BuyerFraudRing, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fraud_ring_memberships')
    role_in_ring = models.CharField(max_length=40, blank=True, default='')
    confidence = models.FloatField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('ring', 'user')]


# ─────────────────────────────────────────────────────────────────
# CH19 — Product recall
# ─────────────────────────────────────────────────────────────────

RECALL_SEVERITY_CHOICES = (
    ('class_1', 'Class 1 — Serious health hazard'),
    ('class_2', 'Class 2 — Temporary health issue'),
    ('class_3', 'Class 3 — Unlikely to cause adverse effect'),
)


class ProductRecall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recall_reference = models.CharField(max_length=40, unique=True)
    product_id = models.CharField(max_length=64, db_index=True)
    affected_listings = models.JSONField(default=list, blank=True)
    severity = models.CharField(max_length=8, choices=RECALL_SEVERITY_CHOICES)
    issue_description = models.TextField()
    recall_source = models.CharField(
        max_length=24,
        choices=(('regulator', 'Regulator (CPSC, EU, etc.)'),
                 ('seller_initiated', 'Seller initiated'),
                 ('platform_initiated', 'Platform initiated'),
                 ('manufacturer', 'Manufacturer')),
    )
    affected_units_estimate = models.PositiveIntegerField(default=0)
    refund_offered = models.BooleanField(default=True)
    replacement_offered = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16, default='announced',
        choices=(('announced', 'Announced'),
                 ('notifying', 'Notifying buyers'),
                 ('refunding', 'Refunds in progress'),
                 ('completed', 'Completed')),
    )
    announced_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class RecallNotification(models.Model):
    id = models.BigAutoField(primary_key=True)
    recall = models.ForeignKey(ProductRecall, on_delete=models.CASCADE, related_name='notifications')
    affected_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recall_notifications')
    order_id = models.CharField(max_length=64, db_index=True)
    channel = models.CharField(max_length=12, default='email')
    sent_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    refund_issued = models.BooleanField(default=False)


# ─────────────────────────────────────────────────────────────────
# CH20 — Export control
# ─────────────────────────────────────────────────────────────────

EXPORT_CONTROL_OUTCOME_CHOICES = (
    ('allowed',           'Allowed'),
    ('licence_required',  'Export licence required'),
    ('blocked',           'Blocked — destination sanctioned'),
    ('manual_review',     'Manual review'),
)


class ExportControlListing(models.Model):
    """One row per (listing, destination_country) eligibility check.
    Blocks ship-to options at quote time."""

    id = models.BigAutoField(primary_key=True)
    listing_id = models.CharField(max_length=64, db_index=True)
    destination_country = models.CharField(max_length=2, db_index=True)
    eccn_classification = models.CharField(max_length=20, blank=True, default='')
    hs_code = models.CharField(max_length=12, blank=True, default='')
    outcome = models.CharField(max_length=20, choices=EXPORT_CONTROL_OUTCOME_CHOICES, default='allowed')
    reason = models.CharField(max_length=255, blank=True, default='')
    last_checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('listing_id', 'destination_country')]


# ─────────────────────────────────────────────────────────────────
# CH21 — Buyer trust score
# ─────────────────────────────────────────────────────────────────

class BuyerTrustScore(models.Model):
    """Composite buyer trust 0-100. Seller trust lives in apps.trust."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='buyer_trust_score')
    score = models.PositiveSmallIntegerField(default=70)
    purchase_history_component = models.FloatField(default=0)
    payment_method_component = models.FloatField(default=0)
    dispute_history_component = models.FloatField(default=0)
    review_quality_component = models.FloatField(default=0)
    account_age_component = models.FloatField(default=0)
    verification_component = models.FloatField(default=0)
    band = models.CharField(
        max_length=20, default='neutral',
        choices=(('trusted_vip', 'Trusted VIP (90-100)'),
                 ('trusted',     'Trusted (75-89)'),
                 ('neutral',     'Neutral (50-74)'),
                 ('cautious',    'Cautious (25-49)'),
                 ('blocked',     'Blocked (0-24)')),
    )
    last_computed_at = models.DateTimeField(auto_now=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Appeals
# ─────────────────────────────────────────────────────────────────

APPEAL_STATUS_CHOICES = (
    ('submitted',          'Submitted'),
    ('under_review',       'Under review'),
    ('approved_reinstated','Approved — reinstated'),
    ('partially_approved', 'Partially approved'),
    ('denied',             'Denied'),
    ('withdrawn',          'Withdrawn'),
)


class AppealRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appellant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appeals_submitted')
    decision_kind = models.CharField(
        max_length=24,
        choices=(('listing_removed', 'Listing removed'),
                 ('account_suspended', 'Account suspended'),
                 ('account_banned', 'Account banned'),
                 ('payout_blocked', 'Payout blocked'),
                 ('review_removed', 'Review removed'),
                 ('other', 'Other')),
    )
    original_decision_reference = models.CharField(max_length=120)
    appeal_text = models.TextField()
    supporting_evidence = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=24, choices=APPEAL_STATUS_CHOICES, default='submitted')
    response_due_at = models.DateTimeField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class AppealDecision(models.Model):
    id = models.BigAutoField(primary_key=True)
    appeal = models.OneToOneField(AppealRequest, on_delete=models.CASCADE, related_name='decision')
    decision = models.CharField(max_length=24)
    decision_reason = models.TextField()
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='appeals_decided',
    )
    decided_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH23 — Law enforcement requests + legal hold
# ─────────────────────────────────────────────────────────────────

LE_REQUEST_KIND_CHOICES = (
    ('subpoena',        'Subpoena'),
    ('search_warrant',  'Search warrant'),
    ('court_order',     'Court order'),
    ('preservation',    'Preservation request'),
    ('emergency_disclosure','Emergency disclosure'),
    ('mlat',            'MLAT'),
    ('regulator',       'Regulator request'),
)

LE_REQUEST_STATUS_CHOICES = (
    ('received',          'Received'),
    ('validating',        'Validating'),
    ('responding',        'Responding'),
    ('responded',         'Responded'),
    ('rejected',          'Rejected'),
    ('challenged_court',  'Challenged in court'),
    ('closed',            'Closed'),
)


class LawEnforcementRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_number = models.CharField(max_length=80, blank=True, default='')
    agency = models.CharField(max_length=120)
    jurisdiction = models.CharField(max_length=2)
    request_kind = models.CharField(max_length=24, choices=LE_REQUEST_KIND_CHOICES)
    subject_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='le_requests_subject',
    )
    legal_document_key = models.CharField(max_length=255, blank=True, default='')
    requested_data = models.JSONField(default=list, blank=True)
    deadline_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=LE_REQUEST_STATUS_CHOICES, default='received')
    response_notes = models.TextField(blank=True, default='')
    handled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='le_requests_handled',
    )
    user_notified = models.BooleanField(
        default=True,
        help_text='Where allowed by law, user is notified. Some warrants '
                  'come with gag orders that prohibit notification.',
    )
    received_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)


class LegalHold(models.Model):
    """Suspends normal data retention for a specific subject so we can
    preserve evidence for ongoing investigations."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    related_request = models.ForeignKey(
        LawEnforcementRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='legal_holds',
    )
    subject_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='legal_holds',
    )
    description = models.TextField()
    scope = models.JSONField(
        default=list, blank=True,
        help_text='Data scopes preserved: orders / messages / payments / etc.',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    expected_release_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ─────────────────────────────────────────────────────────────────

class TrustSafetyKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    prohibited_detections = models.PositiveIntegerField(default=0)
    counterfeit_cases_opened = models.PositiveIntegerField(default=0)
    counterfeit_listings_removed = models.PositiveIntegerField(default=0)
    csam_incidents = models.PositiveIntegerField(default=0)
    hate_speech_actions = models.PositiveIntegerField(default=0)
    ip_complaints_filed = models.PositiveIntegerField(default=0)
    dmca_notices_filed = models.PositiveIntegerField(default=0)
    price_gouging_flags = models.PositiveIntegerField(default=0)
    blacklist_hits = models.PositiveIntegerField(default=0)
    review_fraud_rings = models.PositiveIntegerField(default=0)
    ato_cases = models.PositiveIntegerField(default=0)
    edd_reviews_pending = models.PositiveIntegerField(default=0)
    serial_disputers_flagged = models.PositiveIntegerField(default=0)
    buyer_fraud_rings = models.PositiveIntegerField(default=0)
    recalls_active = models.PositiveIntegerField(default=0)
    appeals_open = models.PositiveIntegerField(default=0)
    le_requests_received = models.PositiveIntegerField(default=0)
    le_requests_overdue = models.PositiveIntegerField(default=0)
    auto_action_rate = models.FloatField(
        default=0,
        help_text='Pct of decisions that fired automatically (no human review).',
    )
    false_positive_rate = models.FloatField(default=0)
    median_response_minutes = models.FloatField(default=0)
    by_category = models.JSONField(default=dict, blank=True)
    by_surface = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class TrustSafetyEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64, db_index=True)
    subject_kind = models.CharField(max_length=24, blank=True, default='')
    subject_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ts_audit_events_subject',
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ts_audit_events_emitted',
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, kind, subject_kind='', subject_id='',
            user=None, actor=None, payload=None):
        try:
            return TrustSafetyEvent.objects.create(
                kind=kind, subject_kind=subject_kind[:24],
                subject_id=subject_id[:64], user=user, actor=actor,
                payload=payload or {},
            )
        except Exception:
            return None
