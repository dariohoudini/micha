"""
Customer Service Operations — data model
========================================

Implements AliExpress_Customer_Service_Operations.docx CH1–CH24.
Existing apps NOT duplicated:

  - apps.chat.Chat / Message (buyer↔seller chat)
  - apps.disputes.Dispute (refund/return dispute)
  - apps.notifications (sends)

What's new here:

  CH1   ServiceChannel, AgentTier
  CH2   HelpArticle, HelpArticleRevision, HelpArticleTag
  CH3-5 SupportTicket + IssueType + TicketEnrichment + TicketSlaPolicy
  CH4   RoutingRule
  CH6   AgentRole, AgentRoleCapability
  CH7   ChatQueue, ChatQueueAssignment
  CH8   ChatbotIntent, ChatbotConversation, ChatbotHandoff
  CH9   CsatSurvey, CsatResponse
  CH10  EscalationRule, EscalationCase
  CH11  RefundAuthorisationRule, RefundReasonCode
  CH12  CompensationRule, CompensationGrant
  CH13  KnowledgeBaseArticle, SmartSuggestion
  CH14  IvrFlow, IvrNode, PhoneCall, CallRecording
  CH15  SellerSupportTicket
  CH16  TrustSafetyReport
  CH17  ProactiveCsTrigger, ProactiveOutreach
  CH18  AgentShiftSchedule, AgentShiftAssignment
  CH19  TranslationCache
  CH20  VipPriorityRoutingRule
  CH21  QaAuditScore
  CH22  TicketVolumeTrend
  CH23  AgentPerformanceMetric, AgentIncentive
  CH24  CsOpsKpiSnapshot
  Audit CsOpsEvent
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
# CH1 — Channels & agent tiers
# ─────────────────────────────────────────────────────────────────

CHANNEL_KIND_CHOICES = (
    ('help_centre', 'Help Centre / self-serve'),
    ('chatbot',     'Chatbot / virtual assistant'),
    ('live_chat',   'Live chat — human agent'),
    ('email',       'Email'),
    ('phone',       'Phone — IVR + agent'),
    ('whatsapp',    'WhatsApp'),
    ('social',      'Social media'),
    ('in_app',      'In-app inbox'),
    ('seller_portal','Seller portal'),
)


class ServiceChannel(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=16, choices=CHANNEL_KIND_CHOICES)
    sla_priority_default = models.PositiveSmallIntegerField(default=3)
    business_hours_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    timezone = models.CharField(max_length=64, default='Africa/Luanda')


AGENT_TIER_CHOICES = (
    ('tier1', 'Tier 1 — Front line'),
    ('tier2', 'Tier 2 — Specialist'),
    ('tier3', 'Tier 3 — Senior / dedicated team'),
    ('tier4', 'Tier 4 — Leadership / exec escalation'),
    ('chatbot','Chatbot / automated'),
)


class AgentTier(models.Model):
    code = models.CharField(max_length=12, primary_key=True, choices=AGENT_TIER_CHOICES)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True, default='')
    max_concurrent_tickets = models.PositiveSmallIntegerField(default=8)
    max_concurrent_chats = models.PositiveSmallIntegerField(default=3)


class CsAgent(models.Model):
    """Profile data for an internal CS agent. The `user` is a regular
    User row tagged with is_staff."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cs_agent')
    tier = models.ForeignKey(AgentTier, on_delete=models.PROTECT, related_name='agents')
    languages = models.JSONField(default=list, blank=True)
    specialisations = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    current_load = models.PositiveSmallIntegerField(default=0)
    timezone = models.CharField(max_length=64, default='Africa/Luanda')
    hired_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH2 — Help Centre
# ─────────────────────────────────────────────────────────────────

ARTICLE_STATUS_CHOICES = (
    ('draft',     'Draft'),
    ('review',    'In review'),
    ('published', 'Published'),
    ('archived',  'Archived'),
)


class HelpArticle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=160)
    title = models.CharField(max_length=255)
    body = models.TextField()
    category = models.CharField(max_length=80, db_index=True)
    language = models.CharField(max_length=10, default='pt-AO', db_index=True)
    status = models.CharField(max_length=12, choices=ARTICLE_STATUS_CHOICES, default='draft')
    view_count = models.PositiveIntegerField(default=0)
    helpful_count = models.PositiveIntegerField(default=0)
    not_helpful_count = models.PositiveIntegerField(default=0)
    related_issue_types = models.JSONField(default=list, blank=True)
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authored_help_articles',
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class HelpArticleRevision(models.Model):
    """Versioning — every edit writes a row so the publish history
    is auditable and rollback is possible."""

    id = models.BigAutoField(primary_key=True)
    article = models.ForeignKey(HelpArticle, on_delete=models.CASCADE, related_name='revisions')
    title = models.CharField(max_length=255)
    body = models.TextField()
    revision_number = models.PositiveIntegerField()
    editor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='edited_help_revisions',
    )
    change_note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('article', 'revision_number')]


class HelpArticleTag(models.Model):
    id = models.BigAutoField(primary_key=True)
    article = models.ForeignKey(HelpArticle, on_delete=models.CASCADE, related_name='tags')
    tag = models.CharField(max_length=80, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH3 — Tickets + issue type taxonomy
# ─────────────────────────────────────────────────────────────────

ISSUE_TYPE_CHOICES = (
    ('order_not_received',  'Order not received'),
    ('order_late',          'Order late / tracking stale'),
    ('item_damaged',        'Item damaged'),
    ('item_wrong',          'Wrong item received'),
    ('item_counterfeit',    'Counterfeit item'),
    ('item_quality',        'Quality issue'),
    ('refund_request',      'Refund request'),
    ('refund_status',       'Refund status'),
    ('return_help',         'Return help'),
    ('payment_problem',     'Payment problem'),
    ('account_problem',     'Account problem'),
    ('shipping_question',   'Shipping question'),
    ('coupon_problem',      'Coupon / promo problem'),
    ('cancel_order',        'Cancel order'),
    ('product_inquiry',     'Product inquiry'),
    ('seller_complaint',    'Seller complaint'),
    ('feedback',            'General feedback'),
    ('other',               'Other'),
)

TICKET_STATUS_CHOICES = (
    ('new',          'New'),
    ('open',         'Open — assigned'),
    ('pending_buyer','Pending buyer'),
    ('pending_seller','Pending seller'),
    ('on_hold',      'On hold — internal'),
    ('resolved',     'Resolved'),
    ('closed',       'Closed'),
    ('reopened',     'Reopened'),
)

TICKET_PRIORITY_CHOICES = (
    (1, 'Critical (P1)'),
    (2, 'High (P2)'),
    (3, 'Medium (P3)'),
    (4, 'Low (P4)'),
)


class SupportTicket(models.Model):
    """The core ticket entity. Every CS interaction across every
    surface becomes a ticket."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket_number = models.CharField(max_length=20, unique=True, db_index=True)
    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='cs_tickets',
    )
    on_behalf_of = models.CharField(
        max_length=12, default='buyer',
        choices=(('buyer', 'Buyer'), ('seller', 'Seller'),
                 ('internal', 'Internal'), ('partner', 'Partner')),
    )
    subject = models.CharField(max_length=255)
    description = models.TextField()
    channel = models.ForeignKey(
        ServiceChannel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets',
    )
    issue_type = models.CharField(
        max_length=24, choices=ISSUE_TYPE_CHOICES, default='other', db_index=True,
    )
    sub_issue_type = models.CharField(max_length=40, blank=True, default='')
    related_order_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    related_product_id = models.CharField(max_length=64, blank=True, default='')
    language = models.CharField(max_length=10, default='pt-AO')
    country = models.CharField(max_length=2, blank=True, default='')
    priority = models.PositiveSmallIntegerField(choices=TICKET_PRIORITY_CHOICES, default=3)
    status = models.CharField(
        max_length=20, choices=TICKET_STATUS_CHOICES, default='new', db_index=True,
    )

    # Assignment.
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_cs_tickets',
    )
    assigned_tier = models.ForeignKey(
        AgentTier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tier_tickets',
    )
    assigned_team = models.CharField(max_length=40, blank=True, default='')
    is_seller_responsibility = models.BooleanField(default=False)

    # SLA + lifecycle.
    first_response_due_at = models.DateTimeField(null=True, blank=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reopened_count = models.PositiveSmallIntegerField(default=0)
    breach_count = models.PositiveSmallIntegerField(default=0)

    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['issue_type', 'status']),
        ]

    @staticmethod
    def make_ticket_number() -> str:
        return f'CS-{timezone.now().strftime("%Y%m%d")}-{secrets.token_hex(3).upper()}'


class TicketMessage(models.Model):
    """A reply on a ticket (from buyer/agent/system)."""

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ticket_messages',
    )
    author_kind = models.CharField(
        max_length=12, default='buyer',
        choices=(('buyer', 'Buyer'), ('agent', 'Agent'),
                 ('seller', 'Seller'), ('system', 'System'),
                 ('chatbot', 'Chatbot')),
    )
    body = models.TextField()
    is_internal_note = models.BooleanField(default=False)
    attachments = models.JSONField(default=list, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)


class TicketEnrichment(models.Model):
    """Auto-populated context on ticket creation (CH3.4) — buyer
    history, related order, prior tickets. Cached for the agent
    interface to read in one query."""

    ticket = models.OneToOneField(SupportTicket, on_delete=models.CASCADE, related_name='enrichment')
    customer_segment = models.CharField(max_length=24, blank=True, default='')
    lifetime_order_count = models.PositiveIntegerField(default=0)
    lifetime_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    prior_ticket_count = models.PositiveIntegerField(default=0)
    open_dispute_count = models.PositiveSmallIntegerField(default=0)
    is_vip = models.BooleanField(default=False)
    related_order_snapshot = models.JSONField(default=dict, blank=True)
    enriched_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH4 — Routing rules
# ─────────────────────────────────────────────────────────────────

class RoutingRule(models.Model):
    """Each rule matches on (issue_type, language, channel, country)
    and routes to a tier + team. Highest priority match wins."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120)
    issue_type = models.CharField(
        max_length=24, choices=ISSUE_TYPE_CHOICES, blank=True, default='',
    )
    channel_code = models.CharField(max_length=24, blank=True, default='')
    language = models.CharField(max_length=10, blank=True, default='')
    country = models.CharField(max_length=2, blank=True, default='')
    target_tier = models.ForeignKey(AgentTier, on_delete=models.CASCADE, related_name='routing_rules')
    target_team = models.CharField(max_length=40, blank=True, default='')
    is_seller_responsibility = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH5 — SLA policies + breach tracking
# ─────────────────────────────────────────────────────────────────

class TicketSlaPolicy(models.Model):
    """Per (priority, channel) SLA target. Used by the scheduler to
    stamp `first_response_due_at` and `resolution_due_at` on creation."""

    id = models.BigAutoField(primary_key=True)
    priority = models.PositiveSmallIntegerField(choices=TICKET_PRIORITY_CHOICES)
    channel_code = models.CharField(max_length=24, blank=True, default='')
    first_response_minutes = models.PositiveIntegerField()
    resolution_minutes = models.PositiveIntegerField()
    business_hours_only = models.BooleanField(default=False)

    class Meta:
        unique_together = [('priority', 'channel_code')]


class TicketSlaBreach(models.Model):
    """One row per SLA missed event (first response or resolution)."""

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='breaches')
    breach_kind = models.CharField(
        max_length=20,
        choices=(('first_response', 'First response'),
                 ('resolution',     'Resolution')),
    )
    breached_at = models.DateTimeField(auto_now_add=True)
    minutes_over = models.PositiveIntegerField()
    escalation_triggered = models.BooleanField(default=False)


# ─────────────────────────────────────────────────────────────────
# CH6 — Agent role capabilities
# ─────────────────────────────────────────────────────────────────

class AgentRole(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)


class AgentRoleCapability(models.Model):
    """Each row = (role, action_code) the role can perform with
    optional amount limits."""

    id = models.BigAutoField(primary_key=True)
    role = models.ForeignKey(AgentRole, on_delete=models.CASCADE, related_name='capabilities')
    action_code = models.CharField(max_length=40, db_index=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    requires_approval = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        unique_together = [('role', 'action_code')]


# ─────────────────────────────────────────────────────────────────
# CH7 — Live chat queue
# ─────────────────────────────────────────────────────────────────

CHAT_QUEUE_STATUS_CHOICES = (
    ('waiting',  'Waiting'),
    ('assigned', 'Assigned'),
    ('active',   'Active'),
    ('ended',    'Ended'),
    ('abandoned','Abandoned'),
    ('transferred','Transferred'),
)


class ChatQueue(models.Model):
    """A waiting room. The dispatcher picks the next agent based on
    skills + load + priority."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='chat_queues')
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_queue_waits')
    channel = models.ForeignKey(ServiceChannel, on_delete=models.PROTECT, related_name='queues')
    priority = models.PositiveSmallIntegerField(default=3, db_index=True)
    requested_skills = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=10, default='pt-AO')
    queue_position = models.PositiveIntegerField(default=0)
    estimated_wait_seconds = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=CHAT_QUEUE_STATUS_CHOICES, default='waiting')
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)


class ChatTransfer(models.Model):
    id = models.BigAutoField(primary_key=True)
    chat_queue = models.ForeignKey(ChatQueue, on_delete=models.CASCADE, related_name='transfers')
    from_agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_transfers_initiated',
    )
    to_agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_transfers_received',
    )
    reason = models.CharField(max_length=120)
    occurred_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH8 — Chatbot
# ─────────────────────────────────────────────────────────────────

class ChatbotIntent(models.Model):
    code = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    sample_utterances = models.JSONField(default=list, blank=True)
    required_entities = models.JSONField(default=list, blank=True)
    response_template = models.TextField(blank=True, default='')
    confidence_threshold = models.FloatField(default=0.7)
    handoff_after_failed_attempts = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)


class ChatbotConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chatbot_conversations',
    )
    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chatbot_conversations',
    )
    detected_intent = models.ForeignKey(
        ChatbotIntent, on_delete=models.SET_NULL, null=True, blank=True,
    )
    last_confidence = models.FloatField(default=0.0)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    resolved = models.BooleanField(default=False)
    handed_off = models.BooleanField(default=False)
    transcript = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)


class ChatbotHandoff(models.Model):
    """When the bot gives up. Captures the reason so we can train the
    classifier on failure patterns."""

    id = models.BigAutoField(primary_key=True)
    conversation = models.OneToOneField(
        ChatbotConversation, on_delete=models.CASCADE, related_name='handoff',
    )
    reason = models.CharField(
        max_length=24,
        choices=(('low_confidence', 'Low confidence'),
                 ('user_request',   'User requested human'),
                 ('failed_attempts','Failed attempts cap'),
                 ('out_of_scope',   'Out of scope'),
                 ('sentiment_negative','Negative sentiment')),
    )
    handed_off_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH9 — CSAT
# ─────────────────────────────────────────────────────────────────

CSAT_DELIVERY_CHOICES = (
    ('email',    'Email'),
    ('push',     'Push'),
    ('in_app',   'In-app'),
    ('sms',      'SMS'),
)


class CsatSurvey(models.Model):
    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='csat_surveys')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='csat_surveys')
    delivery_channel = models.CharField(max_length=10, choices=CSAT_DELIVERY_CHOICES, default='email')
    delivery_token = models.CharField(max_length=32, unique=True, db_index=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    response = models.OneToOneField(
        'CsatResponse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='source_survey',
    )

    @staticmethod
    def make_delivery_token() -> str:
        return secrets.token_urlsafe(16)[:32]


class CsatResponse(models.Model):
    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='csat_responses')
    score = models.PositiveSmallIntegerField(help_text='1-5')
    nps_score = models.SmallIntegerField(
        null=True, blank=True, help_text='0-10 NPS score (optional)',
    )
    comment = models.TextField(blank=True, default='')
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csat_responses_about',
    )
    sentiment = models.CharField(
        max_length=12, blank=True, default='',
        choices=(('positive', 'Positive'), ('neutral', 'Neutral'),
                 ('negative', 'Negative')),
    )
    received_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH10 — Escalation
# ─────────────────────────────────────────────────────────────────

ESCALATION_TRIGGER_CHOICES = (
    ('sla_breach',           'SLA breach'),
    ('reopened_3x',          'Reopened 3 times'),
    ('csat_low',             'Low CSAT received'),
    ('manual_request',       'Manual request'),
    ('vip_customer',         'VIP customer'),
    ('keyword_complaint',    'Keyword match (complaint)'),
    ('repeat_offender',      'Repeat seller offender'),
    ('high_value_order',     'High value order'),
    ('regulator_threat',     'Threat of regulator complaint'),
    ('press_threat',         'Threat of public press'),
)


class EscalationRule(models.Model):
    code = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=120)
    trigger_kind = models.CharField(max_length=20, choices=ESCALATION_TRIGGER_CHOICES)
    target_tier = models.ForeignKey(AgentTier, on_delete=models.PROTECT, related_name='escalation_rules')
    auto_notify_emails = models.JSONField(default=list, blank=True)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)


class EscalationCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='escalations')
    rule = models.ForeignKey(EscalationRule, on_delete=models.PROTECT, related_name='cases')
    triggered_by_kind = models.CharField(max_length=20, choices=ESCALATION_TRIGGER_CHOICES)
    triggered_at = models.DateTimeField(auto_now_add=True)
    target_tier = models.ForeignKey(AgentTier, on_delete=models.PROTECT, related_name='escalation_cases')
    target_agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='escalation_cases',
    )
    status = models.CharField(
        max_length=16, default='triggered',
        choices=(('triggered', 'Triggered'), ('acknowledged', 'Acknowledged'),
                 ('resolved', 'Resolved'), ('rejected', 'Rejected')),
    )
    resolution_notes = models.TextField(blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH11 — Refund authorisation matrix + reason codes
# ─────────────────────────────────────────────────────────────────

class RefundAuthorisationRule(models.Model):
    """A row in the agent × amount × category matrix. The resolver
    picks the cheapest matching rule that authorises the requested
    amount; if none → escalate."""

    id = models.BigAutoField(primary_key=True)
    role = models.ForeignKey(AgentRole, on_delete=models.CASCADE, related_name='refund_rules')
    category = models.CharField(max_length=40, blank=True, default='', db_index=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    requires_approval = models.BooleanField(default=False)
    requires_evidence = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('role', 'category', 'currency')]


REFUND_REASON_KIND_CHOICES = (
    ('not_received',     'Not received'),
    ('damaged',          'Damaged'),
    ('wrong_item',       'Wrong item'),
    ('counterfeit',      'Counterfeit'),
    ('quality_poor',     'Poor quality'),
    ('size_mismatch',    'Size mismatch'),
    ('change_mind',      'Change of mind'),
    ('duplicate_order',  'Duplicate order'),
    ('seller_cancel',    'Seller cancellation'),
    ('platform_error',   'Platform error'),
    ('other',            'Other'),
)


class RefundReasonCode(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    label = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=REFUND_REASON_KIND_CHOICES)
    seller_funded = models.BooleanField(default=True)
    platform_funded = models.BooleanField(default=False)
    requires_return = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH12 — Compensation engine
# ─────────────────────────────────────────────────────────────────

COMPENSATION_TRIGGER_CHOICES = (
    ('order_late',         'Order delivered late'),
    ('not_delivered',      'Not delivered'),
    ('damaged_in_transit', 'Damaged in transit'),
    ('cs_long_wait',       'CS long wait'),
    ('sla_breach',         'CS SLA breach'),
    ('csat_low',           'Low CSAT'),
    ('manual_grant',       'Manual grant'),
)

COMPENSATION_KIND_CHOICES = (
    ('store_credit', 'Store credit'),
    ('coupon',       'Coupon'),
    ('coins',        'Coins'),
    ('cash_refund',  'Cash refund'),
    ('free_shipping','Free shipping voucher'),
)


class CompensationRule(models.Model):
    code = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=120)
    trigger_kind = models.CharField(max_length=20, choices=COMPENSATION_TRIGGER_CHOICES)
    compensation_kind = models.CharField(max_length=14, choices=COMPENSATION_KIND_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)


class CompensationGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compensation_grants',
    )
    rule = models.ForeignKey(CompensationRule, on_delete=models.PROTECT, related_name='grants')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compensation_grants')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    delivered_reference = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(
        max_length=12, default='issued',
        choices=(('issued', 'Issued'), ('redeemed', 'Redeemed'),
                 ('expired', 'Expired'), ('voided', 'Voided')),
    )
    issued_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compensation_grants_issued',
    )
    issued_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH13 — Internal knowledge base
# ─────────────────────────────────────────────────────────────────

class KnowledgeBaseArticle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=160)
    title = models.CharField(max_length=255)
    body = models.TextField()
    category = models.CharField(max_length=80, db_index=True)
    intended_audience = models.CharField(
        max_length=12, default='all_agents',
        choices=(('all_agents', 'All agents'),
                 ('tier1', 'Tier 1 only'),
                 ('tier2_plus', 'Tier 2+'),
                 ('leadership', 'Leadership')),
    )
    related_issue_types = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    view_count = models.PositiveIntegerField(default=0)
    helpful_score = models.IntegerField(default=0)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SmartSuggestion(models.Model):
    """When an agent opens a ticket, the smart-suggestion engine
    writes 1-N rows here matching `issue_type` × buyer history."""

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='smart_suggestions')
    article = models.ForeignKey(KnowledgeBaseArticle, on_delete=models.CASCADE)
    relevance_score = models.FloatField(default=0.0)
    surfaced_at = models.DateTimeField(auto_now_add=True)
    agent_clicked = models.BooleanField(default=False)


# ─────────────────────────────────────────────────────────────────
# CH14 — IVR & phone
# ─────────────────────────────────────────────────────────────────

class IvrFlow(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=120)
    language = models.CharField(max_length=10, default='pt-AO')
    is_active = models.BooleanField(default=True)


class IvrNode(models.Model):
    id = models.BigAutoField(primary_key=True)
    flow = models.ForeignKey(IvrFlow, on_delete=models.CASCADE, related_name='nodes')
    node_key = models.CharField(max_length=40)
    prompt_text = models.TextField()
    is_terminal = models.BooleanField(default=False)
    routing_intent = models.CharField(max_length=40, blank=True, default='')
    children = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [('flow', 'node_key')]


CALL_STATUS_CHOICES = (
    ('queued',     'Queued'),
    ('routing',    'Routing through IVR'),
    ('connected',  'Connected to agent'),
    ('on_hold',    'On hold'),
    ('completed',  'Completed'),
    ('abandoned',  'Abandoned'),
    ('failed',     'Failed'),
)


class PhoneCall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='phone_calls',
    )
    caller_number = models.CharField(max_length=30)
    caller_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='phone_calls',
    )
    ivr_flow = models.ForeignKey(IvrFlow, on_delete=models.SET_NULL, null=True, blank=True)
    ivr_path = models.JSONField(default=list, blank=True)
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='handled_phone_calls',
    )
    status = models.CharField(max_length=12, choices=CALL_STATUS_CHOICES, default='queued')
    queued_at = models.DateTimeField(auto_now_add=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    hold_seconds = models.PositiveIntegerField(default=0)


class CallRecording(models.Model):
    id = models.BigAutoField(primary_key=True)
    call = models.OneToOneField(PhoneCall, on_delete=models.CASCADE, related_name='recording')
    file_key = models.CharField(max_length=255)
    duration_seconds = models.PositiveIntegerField()
    transcript_file_key = models.CharField(max_length=255, blank=True, default='')
    retention_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — Seller support
# ─────────────────────────────────────────────────────────────────

class SellerSupportTicket(models.Model):
    """Sub-class of SupportTicket for seller-facing tickets. We use a
    separate table so the seller portal queries don't have to scan
    over buyer tickets."""

    ticket = models.OneToOneField(SupportTicket, on_delete=models.CASCADE, related_name='seller_extension')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seller_support_tickets')
    seller_tier = models.CharField(max_length=12, blank=True, default='')
    issue_category = models.CharField(
        max_length=24,
        choices=(('account', 'Account'),
                 ('listings', 'Listings'),
                 ('orders', 'Orders'),
                 ('payments', 'Payments'),
                 ('disputes', 'Disputes'),
                 ('policy', 'Policy'),
                 ('appeals', 'Appeals'),
                 ('integrations', 'Integrations')),
    )
    business_impact = models.CharField(
        max_length=12, default='low',
        choices=(('critical', 'Critical — store down'),
                 ('high', 'High'),
                 ('medium', 'Medium'),
                 ('low', 'Low')),
    )


# ─────────────────────────────────────────────────────────────────
# CH16 — Trust & safety escalation
# ─────────────────────────────────────────────────────────────────

class TrustSafetyReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trust_safety_reports',
    )
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ts_reports_made')
    subject_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ts_reports_against',
    )
    subject_product_id = models.CharField(max_length=64, blank=True, default='')
    category = models.CharField(
        max_length=24,
        choices=(('counterfeit', 'Counterfeit'),
                 ('prohibited', 'Prohibited item'),
                 ('fraud', 'Fraud'),
                 ('harassment', 'Harassment'),
                 ('safety_hazard', 'Safety hazard'),
                 ('intellectual_property', 'IP infringement'),
                 ('child_safety', 'Child safety'),
                 ('other', 'Other')),
    )
    severity = models.PositiveSmallIntegerField(default=5)
    description = models.TextField()
    evidence_keys = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16, default='filed',
        choices=(('filed', 'Filed'),
                 ('investigating', 'Investigating'),
                 ('action_taken', 'Action taken'),
                 ('dismissed', 'Dismissed')),
    )
    action_taken = models.CharField(max_length=120, blank=True, default='')
    investigator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ts_reports_investigating',
    )
    filed_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH17 — Proactive CS
# ─────────────────────────────────────────────────────────────────

PROACTIVE_TRIGGER_KIND_CHOICES = (
    ('shipping_stalled',   'Shipping stalled'),
    ('payment_processing_long','Payment processing long'),
    ('high_value_late',    'High value order late'),
    ('repeated_failure',   'Repeated failure'),
    ('mass_outage',        'Mass outage'),
    ('app_crash_cluster',  'App crash cluster'),
)


class ProactiveCsTrigger(models.Model):
    code = models.CharField(max_length=40, primary_key=True)
    kind = models.CharField(max_length=24, choices=PROACTIVE_TRIGGER_KIND_CHOICES)
    description = models.TextField(blank=True, default='')
    condition_config = models.JSONField(default=dict, blank=True)
    outreach_template_key = models.CharField(max_length=64, blank=True, default='')
    is_active = models.BooleanField(default=True)


class ProactiveOutreach(models.Model):
    id = models.BigAutoField(primary_key=True)
    trigger = models.ForeignKey(ProactiveCsTrigger, on_delete=models.PROTECT, related_name='outreaches')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='proactive_outreaches')
    related_order_id = models.CharField(max_length=64, blank=True, default='')
    channel = models.CharField(
        max_length=12, default='push',
        choices=(('email', 'Email'), ('push', 'Push'),
                 ('sms', 'SMS'), ('in_app', 'In-app')),
    )
    payload = models.JSONField(default=dict, blank=True)
    outcome = models.CharField(
        max_length=24, default='sent',
        choices=(('sent', 'Sent'), ('opened', 'Opened'),
                 ('clicked', 'Clicked'),
                 ('escalated_to_ticket', 'Escalated to ticket'),
                 ('failed', 'Failed')),
    )
    occurred_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — Workforce scheduling
# ─────────────────────────────────────────────────────────────────

class AgentShiftSchedule(models.Model):
    id = models.BigAutoField(primary_key=True)
    schedule_date = models.DateField(db_index=True)
    forecasted_volume = models.PositiveIntegerField(default=0)
    forecasted_handle_seconds = models.PositiveIntegerField(default=0)
    required_headcount = models.PositiveSmallIntegerField(default=0)
    actual_headcount = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class AgentShiftAssignment(models.Model):
    id = models.BigAutoField(primary_key=True)
    schedule = models.ForeignKey(AgentShiftSchedule, on_delete=models.CASCADE, related_name='assignments')
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shift_assignments')
    shift_start = models.DateTimeField()
    shift_end = models.DateTimeField()
    breaks_minutes = models.PositiveSmallIntegerField(default=60)
    is_on_call = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)


# ─────────────────────────────────────────────────────────────────
# CH19 — Translation cache
# ─────────────────────────────────────────────────────────────────

class TranslationCache(models.Model):
    """Caches machine + human translations of CS content. Keyed by
    SHA-256 hash of source text + lang pair."""

    cache_key = models.CharField(max_length=64, primary_key=True)
    source_lang = models.CharField(max_length=10)
    target_lang = models.CharField(max_length=10, db_index=True)
    source_text = models.TextField()
    translated_text = models.TextField()
    source = models.CharField(
        max_length=12, default='machine',
        choices=(('machine', 'Machine'),
                 ('human', 'Human'),
                 ('hybrid', 'Hybrid')),
    )
    confidence = models.FloatField(default=0.85)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH20 — VIP routing
# ─────────────────────────────────────────────────────────────────

class VipPriorityRoutingRule(models.Model):
    id = models.BigAutoField(primary_key=True)
    loyalty_tier_required = models.CharField(max_length=24, blank=True, default='')
    min_lifetime_orders = models.PositiveIntegerField(default=0)
    min_lifetime_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_premium_member = models.BooleanField(default=False)
    priority_boost = models.PositiveSmallIntegerField(
        default=1,
        help_text='Drops the priority number by this amount (lower = higher priority).',
    )
    target_tier = models.ForeignKey(AgentTier, on_delete=models.PROTECT, related_name='vip_rules')
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH21 — QA audits
# ─────────────────────────────────────────────────────────────────

class QaAuditScore(models.Model):
    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='qa_audits')
    auditor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='qa_audits_made')
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='qa_audits_received')
    accuracy_score = models.PositiveSmallIntegerField(default=0)
    empathy_score = models.PositiveSmallIntegerField(default=0)
    timeliness_score = models.PositiveSmallIntegerField(default=0)
    compliance_score = models.PositiveSmallIntegerField(default=0)
    overall_score = models.PositiveSmallIntegerField(default=0)
    coaching_notes = models.TextField(blank=True, default='')
    audited_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Ticket volume trend
# ─────────────────────────────────────────────────────────────────

class TicketVolumeTrend(models.Model):
    """Hourly bucket of ticket counts by issue type. Used by the root-
    cause dashboard to spot spikes."""

    id = models.BigAutoField(primary_key=True)
    bucket_start = models.DateTimeField(db_index=True)
    issue_type = models.CharField(max_length=24, choices=ISSUE_TYPE_CHOICES, db_index=True)
    ticket_count = models.PositiveIntegerField(default=0)
    p1_count = models.PositiveIntegerField(default=0)
    breached_count = models.PositiveIntegerField(default=0)
    median_resolution_minutes = models.FloatField(default=0)
    suspected_root_cause = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        unique_together = [('bucket_start', 'issue_type')]


# ─────────────────────────────────────────────────────────────────
# CH23 — Agent performance + incentives
# ─────────────────────────────────────────────────────────────────

class AgentPerformanceMetric(models.Model):
    """Daily metrics per agent."""

    id = models.BigAutoField(primary_key=True)
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cs_performance_metrics')
    snapshot_date = models.DateField(db_index=True)
    tickets_handled = models.PositiveIntegerField(default=0)
    avg_handle_minutes = models.FloatField(default=0)
    first_contact_resolution_pct = models.FloatField(default=0)
    csat_avg = models.FloatField(default=0)
    sla_compliance_pct = models.FloatField(default=0)
    qa_avg = models.FloatField(default=0)
    occupancy_pct = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('agent', 'snapshot_date')]


class AgentIncentive(models.Model):
    id = models.BigAutoField(primary_key=True)
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cs_incentives')
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    reason = models.CharField(max_length=120)
    status = models.CharField(
        max_length=12, default='accrued',
        choices=(('accrued', 'Accrued'), ('paid', 'Paid'),
                 ('clawed_back', 'Clawed back')),
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ─────────────────────────────────────────────────────────────────

class CsOpsKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    tickets_created = models.PositiveIntegerField(default=0)
    tickets_resolved = models.PositiveIntegerField(default=0)
    backlog_count = models.PositiveIntegerField(default=0)
    avg_first_response_minutes = models.FloatField(default=0)
    avg_resolution_minutes = models.FloatField(default=0)
    sla_compliance_pct = models.FloatField(default=0)
    csat_avg = models.FloatField(default=0)
    nps_avg = models.FloatField(default=0)
    first_contact_resolution_pct = models.FloatField(default=0)
    escalation_rate_pct = models.FloatField(default=0)
    chat_abandon_pct = models.FloatField(default=0)
    avg_handle_minutes = models.FloatField(default=0)
    chatbot_deflection_pct = models.FloatField(default=0)
    csat_responses = models.PositiveIntegerField(default=0)
    compensation_count = models.PositiveIntegerField(default=0)
    compensation_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    by_issue_type = models.JSONField(default=dict, blank=True)
    by_channel = models.JSONField(default=dict, blank=True)
    by_tier = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class CsOpsEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64, db_index=True)
    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events',
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cs_audit_events_subject',
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cs_audit_events_emitted',
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, kind, ticket=None, user=None, actor=None, payload=None):
        try:
            return CsOpsEvent.objects.create(
                kind=kind, ticket=ticket, user=user, actor=actor,
                payload=payload or {},
            )
        except Exception:
            return None
