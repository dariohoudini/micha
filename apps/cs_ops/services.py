"""
CS Operations — domain services.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .models import (
    AgentIncentive, AgentPerformanceMetric, AgentRole,
    AgentRoleCapability, AgentTier, ChatQueue, ChatTransfer,
    ChatbotConversation, ChatbotHandoff, ChatbotIntent,
    CompensationGrant, CompensationRule, CsAgent, CsOpsEvent,
    CsOpsKpiSnapshot, CsatResponse, CsatSurvey, EscalationCase,
    EscalationRule, HelpArticle, HelpArticleRevision,
    KnowledgeBaseArticle, PhoneCall, ProactiveCsTrigger,
    ProactiveOutreach, QaAuditScore, RefundAuthorisationRule,
    RefundReasonCode, RoutingRule, ServiceChannel, SmartSuggestion,
    SupportTicket, TicketEnrichment, TicketMessage, TicketSlaBreach,
    TicketSlaPolicy, TicketVolumeTrend, TranslationCache,
    TrustSafetyReport, VipPriorityRoutingRule,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH2 — Help article publishing
# ═══════════════════════════════════════════════════════════════════

def save_help_article_revision(article: HelpArticle, *, editor,
                                  change_note: str = '') -> HelpArticleRevision:
    """Snapshot the current body before save. Production hooks this
    into the article save signal."""
    last_rev = (
        HelpArticleRevision.objects.filter(article=article)
        .order_by('-revision_number').first()
    )
    n = (last_rev.revision_number if last_rev else 0) + 1
    return HelpArticleRevision.objects.create(
        article=article, title=article.title, body=article.body,
        revision_number=n, editor=editor, change_note=change_note,
    )


def publish_help_article(article: HelpArticle, *, editor) -> HelpArticle:
    save_help_article_revision(article, editor=editor,
                                  change_note='publish')
    article.status = 'published'
    article.published_at = timezone.now()
    article.save(update_fields=['status', 'published_at'])
    return article


# ═══════════════════════════════════════════════════════════════════
# CH3 — Ticket creation + enrichment
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def create_ticket(*, requester, subject: str, description: str,
                    channel_code: str = '',
                    issue_type: str = 'other',
                    related_order_id: str = '',
                    related_product_id: str = '',
                    language: str = 'pt-AO',
                    country: str = '',
                    priority: int = 3,
                    on_behalf_of: str = 'buyer') -> SupportTicket:
    channel = None
    if channel_code:
        channel = ServiceChannel.objects.filter(code=channel_code).first()
    ticket = SupportTicket.objects.create(
        ticket_number=SupportTicket.make_ticket_number(),
        requester=requester, on_behalf_of=on_behalf_of,
        subject=subject[:255], description=description,
        channel=channel,
        issue_type=issue_type,
        related_order_id=related_order_id[:64],
        related_product_id=related_product_id[:64],
        language=language[:10], country=country[:2],
        priority=priority,
    )
    enrich_ticket(ticket)
    apply_sla_policy(ticket)
    route_ticket(ticket)
    CsOpsEvent.log(kind='ticket.created', ticket=ticket,
                    actor=requester,
                    payload={'issue_type': issue_type,
                             'priority': priority})
    return ticket


def enrich_ticket(ticket: SupportTicket) -> TicketEnrichment:
    """CH3.4 — populate the side-panel context. Best-effort across
    existing apps; absent apps default to zero."""
    segment = ''
    lifetime_orders = 0
    lifetime_gmv = Decimal('0')
    prior_count = 0
    open_disputes = 0
    is_vip = False
    order_snapshot = {}

    try:
        from apps.buyer_engagement.models import DormancyState, BuyerLTV
        dorm = DormancyState.objects.filter(user=ticket.requester).first()
        ltv = BuyerLTV.objects.filter(user=ticket.requester).first()
        if dorm:
            lifetime_orders = dorm.lifetime_orders
            lifetime_gmv = dorm.lifetime_gmv
        if ltv:
            segment = ltv.segment or ''
            is_vip = ltv.segment in ('VIP', 'High')
    except Exception:
        pass
    try:
        prior_count = SupportTicket.objects.filter(
            requester=ticket.requester,
        ).exclude(pk=ticket.pk).count()
    except Exception:
        pass
    try:
        from apps.disputes.models import Dispute
        open_disputes = Dispute.objects.filter(
            buyer=ticket.requester, status='open',
        ).count()
    except Exception:
        pass
    if ticket.related_order_id:
        try:
            from apps.orders.models import Order
            order = Order.objects.filter(id=ticket.related_order_id).first()
            if order:
                order_snapshot = {
                    'order_id': str(order.id),
                    'status': order.status,
                    'total_amount': str(order.total_amount),
                    'created_at': order.created_at.isoformat(),
                }
        except Exception:
            pass

    obj, _ = TicketEnrichment.objects.update_or_create(
        ticket=ticket,
        defaults={
            'customer_segment': segment[:24],
            'lifetime_order_count': lifetime_orders,
            'lifetime_gmv': lifetime_gmv,
            'prior_ticket_count': prior_count,
            'open_dispute_count': open_disputes,
            'is_vip': is_vip,
            'related_order_snapshot': order_snapshot,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH4 — Routing
# ═══════════════════════════════════════════════════════════════════

def route_ticket(ticket: SupportTicket) -> dict:
    """Walks routing rules in priority order; first match wins.
    Falls back to tier1 if nothing matches."""
    qs = RoutingRule.objects.filter(is_active=True).order_by('priority')
    for rule in qs:
        if rule.issue_type and rule.issue_type != ticket.issue_type:
            continue
        if rule.channel_code and ticket.channel and rule.channel_code != ticket.channel.code:
            continue
        if rule.language and rule.language != ticket.language:
            continue
        if rule.country and rule.country != ticket.country:
            continue
        ticket.assigned_tier = rule.target_tier
        ticket.assigned_team = rule.target_team[:40]
        ticket.is_seller_responsibility = rule.is_seller_responsibility
        if ticket.status == 'new':
            ticket.status = 'open'
        ticket.save(update_fields=[
            'assigned_tier', 'assigned_team',
            'is_seller_responsibility', 'status',
        ])
        # VIP boost if enrichment says so.
        apply_vip_routing(ticket)
        return {'matched_rule': rule.name, 'tier': rule.target_tier_id}

    # Fallback.
    t1 = AgentTier.objects.filter(code='tier1').first()
    if t1:
        ticket.assigned_tier = t1
        ticket.status = 'open' if ticket.status == 'new' else ticket.status
        ticket.save(update_fields=['assigned_tier', 'status'])
        apply_vip_routing(ticket)
    return {'matched_rule': 'fallback', 'tier': 'tier1'}


def apply_vip_routing(ticket: SupportTicket) -> bool:
    """CH20 — boost priority for VIP customers."""
    enrich = TicketEnrichment.objects.filter(ticket=ticket).first()
    if not enrich or not enrich.is_vip:
        return False
    rules = VipPriorityRoutingRule.objects.filter(is_active=True)
    for r in rules:
        if r.min_lifetime_orders and enrich.lifetime_order_count < r.min_lifetime_orders:
            continue
        if r.min_lifetime_gmv and enrich.lifetime_gmv < r.min_lifetime_gmv:
            continue
        new_priority = max(1, ticket.priority - r.priority_boost)
        if new_priority < ticket.priority:
            ticket.priority = new_priority
            ticket.assigned_tier = r.target_tier
            ticket.save(update_fields=['priority', 'assigned_tier'])
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
# CH5 — SLA
# ═══════════════════════════════════════════════════════════════════

def apply_sla_policy(ticket: SupportTicket) -> bool:
    channel_code = ticket.channel.code if ticket.channel else ''
    policy = (
        TicketSlaPolicy.objects.filter(
            priority=ticket.priority, channel_code=channel_code,
        ).first()
        or TicketSlaPolicy.objects.filter(
            priority=ticket.priority, channel_code='',
        ).first()
    )
    if not policy:
        return False
    ticket.first_response_due_at = ticket.created_at + timedelta(
        minutes=policy.first_response_minutes,
    )
    ticket.resolution_due_at = ticket.created_at + timedelta(
        minutes=policy.resolution_minutes,
    )
    ticket.save(update_fields=['first_response_due_at', 'resolution_due_at'])
    return True


def check_and_record_sla_breach(ticket: SupportTicket) -> int:
    """Called by the SLA sweeper. Returns count of new breaches written."""
    n = 0
    now = timezone.now()
    if (ticket.first_response_due_at and not ticket.first_response_at
            and now > ticket.first_response_due_at):
        if not ticket.breaches.filter(breach_kind='first_response').exists():
            TicketSlaBreach.objects.create(
                ticket=ticket, breach_kind='first_response',
                minutes_over=int((now - ticket.first_response_due_at).total_seconds() / 60),
            )
            ticket.breach_count += 1
            ticket.save(update_fields=['breach_count'])
            n += 1
            trigger_escalation(ticket, trigger_kind='sla_breach')
    if (ticket.resolution_due_at and not ticket.resolved_at
            and now > ticket.resolution_due_at):
        if not ticket.breaches.filter(breach_kind='resolution').exists():
            TicketSlaBreach.objects.create(
                ticket=ticket, breach_kind='resolution',
                minutes_over=int((now - ticket.resolution_due_at).total_seconds() / 60),
            )
            ticket.breach_count += 1
            ticket.save(update_fields=['breach_count'])
            n += 1
            trigger_escalation(ticket, trigger_kind='sla_breach')
    return n


# ═══════════════════════════════════════════════════════════════════
# Ticket lifecycle helpers
# ═══════════════════════════════════════════════════════════════════

def reply_to_ticket(*, ticket: SupportTicket, author, body: str,
                     author_kind: str = 'agent',
                     is_internal_note: bool = False,
                     attachments: list = None) -> TicketMessage:
    msg = TicketMessage.objects.create(
        ticket=ticket, author=author, author_kind=author_kind,
        body=body, is_internal_note=is_internal_note,
        attachments=attachments or [],
    )
    if author_kind == 'agent' and not ticket.first_response_at:
        ticket.first_response_at = msg.sent_at
        ticket.save(update_fields=['first_response_at'])
    CsOpsEvent.log(kind='ticket.replied', ticket=ticket, actor=author,
                    payload={'author_kind': author_kind,
                             'internal': is_internal_note})
    return msg


def assign_ticket(ticket: SupportTicket, *, agent) -> SupportTicket:
    ticket.assigned_to = agent
    if ticket.status == 'new':
        ticket.status = 'open'
    ticket.save(update_fields=['assigned_to', 'status'])
    CsOpsEvent.log(kind='ticket.assigned', ticket=ticket, actor=agent,
                    payload={'assignee_id': agent.pk})
    return ticket


def resolve_ticket(ticket: SupportTicket, *, agent,
                     resolution_summary: str = '') -> SupportTicket:
    ticket.status = 'resolved'
    ticket.resolved_at = timezone.now()
    ticket.save(update_fields=['status', 'resolved_at'])
    if resolution_summary:
        reply_to_ticket(ticket=ticket, author=agent,
                          body=resolution_summary,
                          author_kind='agent',
                          is_internal_note=False)
    CsOpsEvent.log(kind='ticket.resolved', ticket=ticket, actor=agent,
                    payload={'duration_seconds':
                              int((ticket.resolved_at - ticket.created_at).total_seconds())})
    return ticket


def close_ticket(ticket: SupportTicket, *, actor) -> SupportTicket:
    ticket.status = 'closed'
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=['status', 'closed_at'])
    # Send CSAT survey.
    send_csat_survey(ticket=ticket)
    return ticket


def reopen_ticket(ticket: SupportTicket, *, actor,
                   reason: str = '') -> SupportTicket:
    ticket.status = 'reopened'
    ticket.reopened_count += 1
    ticket.resolved_at = None
    ticket.closed_at = None
    ticket.save(update_fields=['status', 'reopened_count',
                                'resolved_at', 'closed_at'])
    if ticket.reopened_count >= 3:
        trigger_escalation(ticket, trigger_kind='reopened_3x')
    CsOpsEvent.log(kind='ticket.reopened', ticket=ticket, actor=actor,
                    payload={'count': ticket.reopened_count,
                             'reason': reason})
    return ticket


# ═══════════════════════════════════════════════════════════════════
# CH6 — Agent role authorisation
# ═══════════════════════════════════════════════════════════════════

def agent_can(*, role_code: str, action_code: str,
                amount: Decimal = None) -> dict:
    cap = (
        AgentRoleCapability.objects.filter(
            role__code=role_code, action_code=action_code,
        ).first()
    )
    if not cap:
        return {'allowed': False, 'reason': 'NO_CAPABILITY'}
    if cap.max_amount is not None and amount is not None and amount > cap.max_amount:
        return {'allowed': False, 'reason': 'AMOUNT_OVER_LIMIT',
                'max_amount': str(cap.max_amount),
                'requires_approval': True}
    return {'allowed': True, 'requires_approval': cap.requires_approval}


# ═══════════════════════════════════════════════════════════════════
# CH7 — Chat queue
# ═══════════════════════════════════════════════════════════════════

def join_chat_queue(*, ticket: SupportTicket,
                      channel_code: str = 'live_chat',
                      language: str = 'pt-AO',
                      requested_skills: list = None) -> ChatQueue:
    channel = ServiceChannel.objects.filter(code=channel_code).first()
    position = ChatQueue.objects.filter(
        channel=channel, status='waiting',
    ).count() + 1
    estimated = position * 60  # naive 1 min per queue spot
    return ChatQueue.objects.create(
        ticket=ticket, requester=ticket.requester, channel=channel,
        priority=ticket.priority, language=language[:10],
        requested_skills=requested_skills or [],
        queue_position=position,
        estimated_wait_seconds=estimated,
    )


def assign_chat_from_queue(queue: ChatQueue, *, agent) -> bool:
    if queue.status != 'waiting':
        return False
    queue.status = 'assigned'
    queue.assigned_at = timezone.now()
    queue.save(update_fields=['status', 'assigned_at'])
    assign_ticket(queue.ticket, agent=agent)
    CsOpsEvent.log(kind='chat.assigned', ticket=queue.ticket,
                    actor=agent, payload={'queue_id': str(queue.id)})
    return True


def transfer_chat(queue: ChatQueue, *, from_agent, to_agent,
                    reason: str = '') -> ChatTransfer:
    return ChatTransfer.objects.create(
        chat_queue=queue, from_agent=from_agent, to_agent=to_agent,
        reason=reason[:120],
    )


def end_chat(queue: ChatQueue) -> bool:
    queue.status = 'ended'
    queue.ended_at = timezone.now()
    queue.save(update_fields=['status', 'ended_at'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH8 — Chatbot
# ═══════════════════════════════════════════════════════════════════

def classify_intent(*, utterance: str) -> dict:
    """Cheap deterministic keyword classifier for dev. Production
    swaps in a fine-tuned LM."""
    u = utterance.lower()
    candidates = list(ChatbotIntent.objects.filter(is_active=True))
    best = None
    best_conf = 0.0
    for intent in candidates:
        for sample in (intent.sample_utterances or []):
            s = str(sample).lower()
            if s and s in u:
                conf = 0.85 + (len(s) / max(len(u), 1)) * 0.1
                if conf > best_conf:
                    best = intent
                    best_conf = min(0.99, conf)
        # Bonus: code keyword in utterance.
        code = intent.code.lower().replace('_', ' ')
        if code in u:
            conf = 0.7
            if conf > best_conf:
                best = intent
                best_conf = conf
    return {'intent': best.code if best else None,
            'confidence': best_conf,
            'name': best.name if best else None}


def start_chatbot_conversation(*, user) -> ChatbotConversation:
    return ChatbotConversation.objects.create(user=user)


def append_chatbot_turn(*, conversation: ChatbotConversation,
                           utterance: str) -> dict:
    """Classify + respond.  Returns whatever the dialog policy would
    say.  If handoff conditions are met, also creates a ChatbotHandoff
    row + an attached SupportTicket."""
    classification = classify_intent(utterance=utterance)
    transcript = conversation.transcript or []
    transcript.append({'who': 'user', 'text': utterance,
                        'at': timezone.now().isoformat()})
    response_text = None
    if classification['intent']:
        intent = ChatbotIntent.objects.get(code=classification['intent'])
        if classification['confidence'] >= intent.confidence_threshold:
            response_text = intent.response_template or 'Estamos a tratar do seu pedido.'
            conversation.detected_intent = intent
            conversation.last_confidence = classification['confidence']
        else:
            conversation.failed_attempts += 1
    else:
        conversation.failed_attempts += 1

    handed_off = False
    if response_text is None:
        response_text = ('Não tenho a certeza de como o ajudar. Vou '
                          'pedir a um agente humano.')
        if conversation.failed_attempts >= 2:
            handed_off = _do_handoff(conversation, reason='failed_attempts')

    transcript.append({'who': 'bot', 'text': response_text,
                        'at': timezone.now().isoformat()})
    conversation.transcript = transcript
    conversation.save(update_fields=[
        'transcript', 'failed_attempts',
        'detected_intent', 'last_confidence',
    ])
    return {'response': response_text,
            'intent': classification['intent'],
            'confidence': classification['confidence'],
            'handed_off': handed_off,
            'ticket_id': str(conversation.ticket_id) if conversation.ticket else None}


def _do_handoff(conversation: ChatbotConversation,
                  *, reason: str) -> bool:
    if conversation.handed_off or not conversation.user:
        conversation.handed_off = True
        conversation.save(update_fields=['handed_off'])
        return True
    ticket = create_ticket(
        requester=conversation.user,
        subject='Conversa transferida do chatbot',
        description='Ver transcrição completa em ChatbotConversation.',
        channel_code='chatbot',
        issue_type='other', priority=3,
    )
    ChatbotHandoff.objects.create(conversation=conversation, reason=reason)
    conversation.ticket = ticket
    conversation.handed_off = True
    conversation.save(update_fields=['ticket', 'handed_off'])
    join_chat_queue(ticket=ticket, channel_code='live_chat',
                      language=conversation.user and 'pt-AO')
    return True


# ═══════════════════════════════════════════════════════════════════
# CH9 — CSAT
# ═══════════════════════════════════════════════════════════════════

def send_csat_survey(*, ticket: SupportTicket,
                       delivery_channel: str = 'email',
                       valid_days: int = 14) -> CsatSurvey:
    return CsatSurvey.objects.create(
        ticket=ticket, recipient=ticket.requester,
        delivery_channel=delivery_channel,
        delivery_token=CsatSurvey.make_delivery_token(),
        expires_at=timezone.now() + timedelta(days=valid_days),
    )


def submit_csat(*, survey_token: str, score: int, comment: str = '',
                  nps_score: int = None) -> CsatResponse:
    survey = CsatSurvey.objects.filter(delivery_token=survey_token).first()
    if not survey:
        raise ValueError('UNKNOWN_TOKEN')
    if survey.expires_at < timezone.now():
        raise ValueError('TOKEN_EXPIRED')
    if survey.response_id:
        raise ValueError('ALREADY_SUBMITTED')
    sentiment = ('positive' if score >= 4
                  else 'neutral' if score == 3 else 'negative')
    resp = CsatResponse.objects.create(
        ticket=survey.ticket, score=score, nps_score=nps_score,
        comment=comment[:5000],
        agent=survey.ticket.assigned_to,
        sentiment=sentiment,
    )
    survey.response = resp
    survey.save(update_fields=['response'])
    if score <= 2:
        trigger_escalation(survey.ticket, trigger_kind='csat_low')
    return resp


# ═══════════════════════════════════════════════════════════════════
# CH10 — Escalation
# ═══════════════════════════════════════════════════════════════════

def trigger_escalation(ticket: SupportTicket, *, trigger_kind: str,
                         rule_code: str = '') -> EscalationCase | None:
    rule = (
        EscalationRule.objects.filter(code=rule_code, is_active=True).first()
        if rule_code else
        EscalationRule.objects.filter(
            trigger_kind=trigger_kind, is_active=True,
        ).first()
    )
    if not rule:
        return None
    case = EscalationCase.objects.create(
        ticket=ticket, rule=rule, triggered_by_kind=trigger_kind,
        target_tier=rule.target_tier,
    )
    ticket.assigned_tier = rule.target_tier
    ticket.save(update_fields=['assigned_tier'])
    CsOpsEvent.log(kind='ticket.escalated', ticket=ticket,
                    payload={'rule': rule.code, 'kind': trigger_kind})
    return case


# ═══════════════════════════════════════════════════════════════════
# CH11 — Refund authorisation
# ═══════════════════════════════════════════════════════════════════

def authorise_refund(*, role_code: str, category: str,
                       amount: Decimal,
                       currency: str = 'AOA') -> dict:
    qs = RefundAuthorisationRule.objects.filter(
        role__code=role_code, is_active=True, currency=currency,
    ).filter(
        django_models.Q(category=category) | django_models.Q(category='')
    ).order_by('-max_amount')
    rule = qs.first()
    if not rule:
        return {'allowed': False, 'reason': 'NO_RULE'}
    if amount > rule.max_amount:
        return {'allowed': False, 'reason': 'OVER_LIMIT',
                'max_amount': str(rule.max_amount),
                'requires_escalation': True}
    return {'allowed': True,
            'requires_approval': rule.requires_approval,
            'requires_evidence': rule.requires_evidence}


# ═══════════════════════════════════════════════════════════════════
# CH12 — Compensation engine
# ═══════════════════════════════════════════════════════════════════

def grant_compensation(*, ticket: SupportTicket, rule_code: str,
                          actor=None,
                          override_amount: Decimal = None) -> CompensationGrant:
    rule = CompensationRule.objects.filter(code=rule_code, is_active=True).first()
    if not rule:
        raise ValueError('RULE_NOT_FOUND')
    amount = override_amount if override_amount is not None else rule.amount
    grant = CompensationGrant.objects.create(
        ticket=ticket, rule=rule,
        recipient=ticket.requester if ticket else None,
        amount=amount, currency=rule.currency,
        issued_by=actor,
    )
    # Bridge to existing systems based on kind.
    try:
        if rule.compensation_kind == 'store_credit':
            from apps.payment_ops.services import grant_store_credit
            grant_store_credit(
                user=grant.recipient, amount=amount,
                reason='cs_compensation', currency=rule.currency,
                related_order_id=ticket.related_order_id if ticket else '',
                granted_by=actor,
            )
            grant.delivered_reference = 'store_credit:granted'
        elif rule.compensation_kind == 'coupon':
            from apps.marketing_engine.models import MePromotion
            promo = MePromotion.objects.create(
                type='platform_coupon', name='CS compensation',
                funded_by='platform', discount_type='fixed_amount',
                discount_value=amount, currency=rule.currency,
                distribution_method='targeted',
                target_segment=f'user:{grant.recipient.pk}',
                coupon_code=f'CS-{secrets.token_urlsafe(6)[:8].upper()}',
                valid_from=timezone.now(),
                valid_until=timezone.now() + timedelta(days=30),
                status='active', max_uses_per_user=1,
            )
            grant.delivered_reference = f'coupon:{promo.coupon_code}'
        elif rule.compensation_kind == 'coins':
            try:
                from apps.loyalty.models import PointsTransaction
                PointsTransaction.objects.create(
                    user=grant.recipient, points=int(amount),
                    reason='cs_compensation',
                )
            except Exception:
                pass
            grant.delivered_reference = 'coins:granted'
        grant.save(update_fields=['delivered_reference'])
    except Exception as e:
        log.exception('compensation grant delivery failed: %s', e)

    CsOpsEvent.log(kind='compensation.granted', ticket=ticket,
                    actor=actor,
                    payload={'rule': rule.code, 'amount': str(amount)})
    return grant


# ═══════════════════════════════════════════════════════════════════
# CH13 — KB smart suggestions
# ═══════════════════════════════════════════════════════════════════

def surface_smart_suggestions(ticket: SupportTicket, *,
                                 max_n: int = 5) -> list[SmartSuggestion]:
    """Pick KB articles whose related_issue_types include this
    ticket's issue type, ranked by helpful_score."""
    qs = KnowledgeBaseArticle.objects.filter(is_active=True)
    relevant = []
    for article in qs:
        if (article.related_issue_types
                and ticket.issue_type in article.related_issue_types):
            score = float(article.helpful_score) + (article.view_count * 0.01)
            relevant.append((score, article))
    relevant.sort(key=lambda t: t[0], reverse=True)
    out = []
    for score, article in relevant[:max_n]:
        ss = SmartSuggestion.objects.create(
            ticket=ticket, article=article, relevance_score=score,
        )
        out.append(ss)
    return out


# ═══════════════════════════════════════════════════════════════════
# CH14 — Phone call
# ═══════════════════════════════════════════════════════════════════

def start_phone_call(*, caller_number: str, ivr_flow_code: str = '',
                       caller_user=None) -> PhoneCall:
    from .models import IvrFlow
    flow = IvrFlow.objects.filter(code=ivr_flow_code).first() if ivr_flow_code else None
    return PhoneCall.objects.create(
        caller_number=caller_number[:30],
        caller_user=caller_user, ivr_flow=flow,
    )


def end_phone_call(call: PhoneCall, *, status: str = 'completed') -> PhoneCall:
    now = timezone.now()
    call.status = status
    call.ended_at = now
    if call.queued_at:
        call.duration_seconds = max(0, int((now - call.queued_at).total_seconds()))
    call.save(update_fields=['status', 'ended_at', 'duration_seconds'])
    return call


# ═══════════════════════════════════════════════════════════════════
# CH16 — Trust & safety
# ═══════════════════════════════════════════════════════════════════

def file_trust_safety_report(*, reporter,
                                 category: str,
                                 description: str,
                                 ticket: SupportTicket = None,
                                 subject_user=None,
                                 subject_product_id: str = '',
                                 severity: int = 5,
                                 evidence_keys: list = None) -> TrustSafetyReport:
    return TrustSafetyReport.objects.create(
        ticket=ticket, reporter=reporter, subject_user=subject_user,
        subject_product_id=subject_product_id[:64],
        category=category, severity=severity,
        description=description[:10000],
        evidence_keys=evidence_keys or [],
    )


# ═══════════════════════════════════════════════════════════════════
# CH17 — Proactive CS
# ═══════════════════════════════════════════════════════════════════

def proactive_outreach(*, trigger_code: str, recipient,
                          related_order_id: str = '',
                          payload: dict = None,
                          channel: str = 'push') -> ProactiveOutreach:
    trigger = ProactiveCsTrigger.objects.filter(code=trigger_code, is_active=True).first()
    if not trigger:
        raise ValueError('TRIGGER_NOT_FOUND')
    return ProactiveOutreach.objects.create(
        trigger=trigger, recipient=recipient,
        related_order_id=related_order_id[:64],
        channel=channel, payload=payload or {},
    )


# ═══════════════════════════════════════════════════════════════════
# CH19 — Translation cache
# ═══════════════════════════════════════════════════════════════════

def translate_text(*, source_text: str, source_lang: str,
                     target_lang: str) -> dict:
    key = hashlib.sha256(
        f'{source_lang}|{target_lang}|{source_text}'.encode()
    ).hexdigest()
    existing = TranslationCache.objects.filter(cache_key=key).first()
    if existing:
        return {'translated_text': existing.translated_text,
                'source': existing.source,
                'confidence': existing.confidence, 'cached': True}
    # Production wires Google / DeepL / internal model. Dev returns
    # marker echo.
    translated = f'[{target_lang.upper()}] {source_text}'
    obj = TranslationCache.objects.create(
        cache_key=key, source_lang=source_lang,
        target_lang=target_lang, source_text=source_text[:10000],
        translated_text=translated[:10000],
        source='machine', confidence=0.7,
    )
    return {'translated_text': obj.translated_text,
            'source': obj.source,
            'confidence': obj.confidence, 'cached': False}


# ═══════════════════════════════════════════════════════════════════
# CH18 — Workforce schedule
# ═══════════════════════════════════════════════════════════════════

def plan_shift_schedule(*, schedule_date,
                           forecasted_volume: int = 0,
                           target_handle_seconds: int = 480) -> 'AgentShiftSchedule':
    from .models import AgentShiftSchedule
    # Erlang-C-lite: required_headcount = forecast × handle / (3600 * occupancy_target).
    occupancy_target = 0.80
    required = int(round(
        max(forecasted_volume, 0) * target_handle_seconds /
        (3600 * occupancy_target)
    ))
    obj, _ = AgentShiftSchedule.objects.update_or_create(
        schedule_date=schedule_date,
        defaults={
            'forecasted_volume': forecasted_volume,
            'forecasted_handle_seconds': target_handle_seconds,
            'required_headcount': required,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH22 — Ticket trend rollup
# ═══════════════════════════════════════════════════════════════════

def snapshot_ticket_trends(*, hours_back: int = 1) -> int:
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    bucket_start = now - timedelta(hours=hours_back)
    bucket_end = bucket_start + timedelta(hours=1)
    qs = SupportTicket.objects.filter(
        created_at__gte=bucket_start, created_at__lt=bucket_end,
    )
    rows = {}
    for t in qs:
        agg = rows.setdefault(t.issue_type, {'count': 0, 'p1': 0,
                                              'breached': 0, 'durations': []})
        agg['count'] += 1
        if t.priority == 1:
            agg['p1'] += 1
        if t.breach_count > 0:
            agg['breached'] += 1
        if t.resolved_at:
            agg['durations'].append(
                (t.resolved_at - t.created_at).total_seconds() / 60.0,
            )
    n = 0
    for issue_type, a in rows.items():
        median = 0
        if a['durations']:
            s = sorted(a['durations'])
            median = s[len(s) // 2]
        TicketVolumeTrend.objects.update_or_create(
            bucket_start=bucket_start, issue_type=issue_type,
            defaults={
                'ticket_count': a['count'],
                'p1_count': a['p1'],
                'breached_count': a['breached'],
                'median_resolution_minutes': median,
            },
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH23 — Agent performance + incentives
# ═══════════════════════════════════════════════════════════════════

def snapshot_agent_performance(*, snapshot_date=None) -> int:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)
    agents = User.objects.filter(
        assigned_cs_tickets__updated_at__gte=start,
        assigned_cs_tickets__updated_at__lt=end,
    ).distinct()
    n = 0
    for agent in agents:
        tickets = SupportTicket.objects.filter(
            assigned_to=agent, updated_at__gte=start, updated_at__lt=end,
        )
        n_tickets = tickets.count()
        durations = [
            (t.resolved_at - t.created_at).total_seconds() / 60.0
            for t in tickets if t.resolved_at
        ]
        avg_handle = sum(durations) / len(durations) if durations else 0
        fcr = (tickets.filter(reopened_count=0, status='resolved').count()
               / n_tickets * 100) if n_tickets else 0
        sla = (tickets.filter(breach_count=0).count() / n_tickets * 100) if n_tickets else 0
        csat_qs = CsatResponse.objects.filter(
            agent=agent, received_at__gte=start, received_at__lt=end,
        )
        csat_avg = csat_qs.aggregate(a=django_models.Avg('score'))['a'] or 0
        qa_qs = QaAuditScore.objects.filter(
            agent=agent, audited_at__gte=start, audited_at__lt=end,
        )
        qa_avg = qa_qs.aggregate(a=django_models.Avg('overall_score'))['a'] or 0
        AgentPerformanceMetric.objects.update_or_create(
            agent=agent, snapshot_date=snapshot_date,
            defaults={
                'tickets_handled': n_tickets,
                'avg_handle_minutes': avg_handle,
                'first_contact_resolution_pct': fcr,
                'csat_avg': float(csat_avg),
                'sla_compliance_pct': sla,
                'qa_avg': float(qa_avg),
                'occupancy_pct': 0,
            },
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_cs_ops_kpis(snapshot_date=None) -> CsOpsKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)
    created = SupportTicket.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    resolved_qs = SupportTicket.objects.filter(
        resolved_at__gte=start, resolved_at__lt=end,
    )
    resolved = resolved_qs.count()
    backlog = SupportTicket.objects.filter(
        status__in=('new', 'open', 'pending_buyer',
                     'pending_seller', 'on_hold'),
    ).count()
    first_resp_minutes = [
        (t.first_response_at - t.created_at).total_seconds() / 60.0
        for t in resolved_qs if t.first_response_at
    ]
    res_minutes = [
        (t.resolved_at - t.created_at).total_seconds() / 60.0
        for t in resolved_qs if t.resolved_at
    ]
    avg_first = sum(first_resp_minutes) / len(first_resp_minutes) if first_resp_minutes else 0
    avg_res = sum(res_minutes) / len(res_minutes) if res_minutes else 0
    sla_ok = resolved_qs.filter(breach_count=0).count()
    sla_pct = (sla_ok / resolved * 100) if resolved else 0
    csat_qs = CsatResponse.objects.filter(received_at__gte=start, received_at__lt=end)
    csat_count = csat_qs.count()
    csat_avg = csat_qs.aggregate(a=django_models.Avg('score'))['a'] or 0
    nps_avg = csat_qs.aggregate(a=django_models.Avg('nps_score'))['a'] or 0
    escalations = EscalationCase.objects.filter(
        triggered_at__gte=start, triggered_at__lt=end,
    ).count()
    esc_pct = (escalations / created * 100) if created else 0
    chat_total = ChatQueue.objects.filter(
        queued_at__gte=start, queued_at__lt=end,
    ).count()
    chat_aban = ChatQueue.objects.filter(
        queued_at__gte=start, queued_at__lt=end,
        status='abandoned',
    ).count()
    chat_aban_pct = (chat_aban / chat_total * 100) if chat_total else 0
    bot_total = ChatbotConversation.objects.filter(
        started_at__gte=start, started_at__lt=end,
    ).count()
    bot_resolved = ChatbotConversation.objects.filter(
        started_at__gte=start, started_at__lt=end, resolved=True,
        handed_off=False,
    ).count()
    bot_pct = (bot_resolved / bot_total * 100) if bot_total else 0
    comp_qs = CompensationGrant.objects.filter(
        issued_at__gte=start, issued_at__lt=end,
    )
    comp_count = comp_qs.count()
    comp_amount = comp_qs.aggregate(s=django_models.Sum('amount'))['s'] or Decimal('0')
    fcr = (resolved_qs.filter(reopened_count=0).count() / resolved * 100) if resolved else 0
    by_issue = dict(
        SupportTicket.objects.filter(created_at__gte=start, created_at__lt=end)
        .values_list('issue_type').annotate(c=django_models.Count('id'))
    )

    obj, _ = CsOpsKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'tickets_created': created,
            'tickets_resolved': resolved,
            'backlog_count': backlog,
            'avg_first_response_minutes': avg_first,
            'avg_resolution_minutes': avg_res,
            'sla_compliance_pct': sla_pct,
            'csat_avg': float(csat_avg),
            'nps_avg': float(nps_avg or 0),
            'first_contact_resolution_pct': fcr,
            'escalation_rate_pct': esc_pct,
            'chat_abandon_pct': chat_aban_pct,
            'avg_handle_minutes': avg_res,
            'chatbot_deflection_pct': bot_pct,
            'csat_responses': csat_count,
            'compensation_count': comp_count,
            'compensation_amount': comp_amount,
            'by_issue_type': {k or '': v for k, v in by_issue.items()},
        },
    )
    return obj
