from django.contrib import admin

from .models import (
    AgentIncentive, AgentPerformanceMetric, AgentRole,
    AgentRoleCapability, AgentShiftAssignment, AgentShiftSchedule,
    AgentTier, CallRecording, ChatQueue, ChatTransfer,
    ChatbotConversation, ChatbotHandoff, ChatbotIntent,
    CompensationGrant, CompensationRule, CsAgent, CsOpsEvent,
    CsOpsKpiSnapshot, CsatResponse, CsatSurvey, EscalationCase,
    EscalationRule, HelpArticle, HelpArticleRevision,
    HelpArticleTag, IvrFlow, IvrNode, KnowledgeBaseArticle,
    PhoneCall, ProactiveCsTrigger, ProactiveOutreach,
    QaAuditScore, RefundAuthorisationRule, RefundReasonCode,
    RoutingRule, SellerSupportTicket, ServiceChannel,
    SmartSuggestion, SupportTicket, TicketEnrichment,
    TicketMessage, TicketSlaBreach, TicketSlaPolicy,
    TicketVolumeTrend, TranslationCache, TrustSafetyReport,
    VipPriorityRoutingRule,
)


@admin.register(ServiceChannel)
class ServiceChannelAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'kind', 'sla_priority_default',
                    'business_hours_only', 'is_active')


@admin.register(AgentTier)
class AgentTierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'max_concurrent_tickets',
                    'max_concurrent_chats')


@admin.register(CsAgent)
class CsAgentAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'is_available',
                    'current_load', 'languages')
    list_filter = ('tier', 'is_active', 'is_available')


@admin.register(HelpArticle)
class HelpArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'language', 'status',
                    'view_count', 'helpful_count')
    list_filter = ('status', 'language', 'category')
    search_fields = ('title', 'slug')


@admin.register(HelpArticleRevision)
class HelpArticleRevisionAdmin(admin.ModelAdmin):
    list_display = ('article', 'revision_number', 'editor', 'created_at')


@admin.register(HelpArticleTag)
class HelpArticleTagAdmin(admin.ModelAdmin):
    list_display = ('article', 'tag')


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'subject', 'requester',
                    'issue_type', 'priority', 'status',
                    'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'issue_type', 'on_behalf_of')
    search_fields = ('ticket_number', 'subject', 'related_order_id')


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'author_kind', 'author',
                    'is_internal_note', 'sent_at')
    list_filter = ('author_kind', 'is_internal_note')


@admin.register(TicketEnrichment)
class TicketEnrichmentAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'customer_segment',
                    'lifetime_order_count', 'lifetime_gmv',
                    'open_dispute_count', 'is_vip')


@admin.register(RoutingRule)
class RoutingRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'issue_type', 'channel_code',
                    'language', 'country', 'target_tier',
                    'priority', 'is_active')
    list_filter = ('is_active', 'target_tier')


@admin.register(TicketSlaPolicy)
class TicketSlaPolicyAdmin(admin.ModelAdmin):
    list_display = ('priority', 'channel_code',
                    'first_response_minutes', 'resolution_minutes')
    list_filter = ('priority',)


@admin.register(TicketSlaBreach)
class TicketSlaBreachAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'breach_kind', 'minutes_over',
                    'escalation_triggered', 'breached_at')


@admin.register(AgentRole)
class AgentRoleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')


@admin.register(AgentRoleCapability)
class AgentRoleCapabilityAdmin(admin.ModelAdmin):
    list_display = ('role', 'action_code', 'max_amount', 'requires_approval')


@admin.register(ChatQueue)
class ChatQueueAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'requester', 'priority',
                    'queue_position', 'status', 'queued_at')
    list_filter = ('status',)


@admin.register(ChatTransfer)
class ChatTransferAdmin(admin.ModelAdmin):
    list_display = ('chat_queue', 'from_agent', 'to_agent',
                    'reason', 'occurred_at')


@admin.register(ChatbotIntent)
class ChatbotIntentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'confidence_threshold',
                    'handoff_after_failed_attempts', 'is_active')
    list_filter = ('is_active',)


@admin.register(ChatbotConversation)
class ChatbotConversationAdmin(admin.ModelAdmin):
    list_display = ('user', 'detected_intent', 'last_confidence',
                    'failed_attempts', 'resolved', 'handed_off')
    list_filter = ('resolved', 'handed_off')


@admin.register(ChatbotHandoff)
class ChatbotHandoffAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'reason', 'handed_off_at')
    list_filter = ('reason',)


@admin.register(CsatSurvey)
class CsatSurveyAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'recipient', 'delivery_channel',
                    'sent_at', 'expires_at')


@admin.register(CsatResponse)
class CsatResponseAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'score', 'sentiment',
                    'agent', 'received_at')
    list_filter = ('score', 'sentiment')


@admin.register(EscalationRule)
class EscalationRuleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'trigger_kind',
                    'target_tier', 'is_active')
    list_filter = ('trigger_kind', 'is_active')


@admin.register(EscalationCase)
class EscalationCaseAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'rule', 'triggered_by_kind',
                    'target_tier', 'status', 'triggered_at')
    list_filter = ('status', 'triggered_by_kind')


@admin.register(RefundAuthorisationRule)
class RefundAuthorisationRuleAdmin(admin.ModelAdmin):
    list_display = ('role', 'category', 'max_amount', 'currency',
                    'requires_approval', 'requires_evidence')


@admin.register(RefundReasonCode)
class RefundReasonCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'label', 'kind',
                    'seller_funded', 'platform_funded',
                    'requires_return')


@admin.register(CompensationRule)
class CompensationRuleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'trigger_kind',
                    'compensation_kind', 'amount', 'currency',
                    'is_active')
    list_filter = ('trigger_kind', 'compensation_kind', 'is_active')


@admin.register(CompensationGrant)
class CompensationGrantAdmin(admin.ModelAdmin):
    list_display = ('rule', 'recipient', 'amount', 'currency',
                    'status', 'issued_at')
    list_filter = ('status',)


@admin.register(KnowledgeBaseArticle)
class KnowledgeBaseArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'intended_audience',
                    'view_count', 'helpful_score', 'is_active')
    list_filter = ('intended_audience', 'is_active')


@admin.register(SmartSuggestion)
class SmartSuggestionAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'article', 'relevance_score',
                    'agent_clicked', 'surfaced_at')


@admin.register(IvrFlow)
class IvrFlowAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'language', 'is_active')


@admin.register(IvrNode)
class IvrNodeAdmin(admin.ModelAdmin):
    list_display = ('flow', 'node_key', 'is_terminal', 'routing_intent')


@admin.register(PhoneCall)
class PhoneCallAdmin(admin.ModelAdmin):
    list_display = ('caller_number', 'caller_user', 'agent',
                    'status', 'duration_seconds', 'queued_at')
    list_filter = ('status',)


@admin.register(CallRecording)
class CallRecordingAdmin(admin.ModelAdmin):
    list_display = ('call', 'duration_seconds', 'retention_until')


@admin.register(SellerSupportTicket)
class SellerSupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'seller', 'seller_tier',
                    'issue_category', 'business_impact')
    list_filter = ('issue_category', 'business_impact')


@admin.register(TrustSafetyReport)
class TrustSafetyReportAdmin(admin.ModelAdmin):
    list_display = ('reporter', 'category', 'severity',
                    'status', 'filed_at')
    list_filter = ('category', 'status')


@admin.register(ProactiveCsTrigger)
class ProactiveCsTriggerAdmin(admin.ModelAdmin):
    list_display = ('code', 'kind', 'is_active')
    list_filter = ('kind', 'is_active')


@admin.register(ProactiveOutreach)
class ProactiveOutreachAdmin(admin.ModelAdmin):
    list_display = ('trigger', 'recipient', 'channel',
                    'outcome', 'occurred_at')
    list_filter = ('channel', 'outcome')


@admin.register(AgentShiftSchedule)
class AgentShiftScheduleAdmin(admin.ModelAdmin):
    list_display = ('schedule_date', 'forecasted_volume',
                    'required_headcount', 'actual_headcount')


@admin.register(AgentShiftAssignment)
class AgentShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ('schedule', 'agent', 'shift_start',
                    'shift_end', 'confirmed')


@admin.register(TranslationCache)
class TranslationCacheAdmin(admin.ModelAdmin):
    list_display = ('source_lang', 'target_lang',
                    'source', 'confidence', 'created_at')
    list_filter = ('source_lang', 'target_lang', 'source')


@admin.register(VipPriorityRoutingRule)
class VipPriorityRoutingRuleAdmin(admin.ModelAdmin):
    list_display = ('loyalty_tier_required', 'min_lifetime_gmv',
                    'priority_boost', 'target_tier', 'is_active')


@admin.register(QaAuditScore)
class QaAuditScoreAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'agent', 'auditor',
                    'overall_score', 'audited_at')


@admin.register(TicketVolumeTrend)
class TicketVolumeTrendAdmin(admin.ModelAdmin):
    list_display = ('bucket_start', 'issue_type',
                    'ticket_count', 'p1_count', 'breached_count')
    list_filter = ('issue_type',)


@admin.register(AgentPerformanceMetric)
class AgentPerformanceMetricAdmin(admin.ModelAdmin):
    list_display = ('agent', 'snapshot_date', 'tickets_handled',
                    'csat_avg', 'sla_compliance_pct',
                    'qa_avg', 'occupancy_pct')


@admin.register(AgentIncentive)
class AgentIncentiveAdmin(admin.ModelAdmin):
    list_display = ('agent', 'period_start', 'period_end',
                    'amount', 'currency', 'status')
    list_filter = ('status',)


@admin.register(CsOpsKpiSnapshot)
class CsOpsKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'tickets_created',
                    'tickets_resolved', 'sla_compliance_pct',
                    'csat_avg', 'chatbot_deflection_pct')


@admin.register(CsOpsEvent)
class CsOpsEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'ticket', 'user', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at',
                       'ticket', 'user', 'actor')
