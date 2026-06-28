"""
CS Operations REST surface — thin views over services.py.
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AgentPerformanceMetric, AgentRole, ChatQueue,
    ChatbotConversation, CompensationGrant, CompensationRule,
    CsOpsEvent, CsOpsKpiSnapshot, CsatResponse, CsatSurvey,
    EscalationCase, HelpArticle, KnowledgeBaseArticle, PhoneCall,
    ProactiveCsTrigger, QaAuditScore, ServiceChannel,
    SupportTicket, TicketMessage, TicketVolumeTrend,
    TrustSafetyReport,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH2 — Help articles ──────────────────────────────────────

class HelpArticleListCreateView(generics.ListCreateAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = HelpArticle.objects.filter(status='published')
        cat = self.request.query_params.get('category')
        if cat:
            qs = qs.filter(category=cat)
        lang = self.request.query_params.get('language')
        if lang:
            qs = qs.filter(language=lang)
        return qs

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'slug', 'title', 'category', 'language',
            'view_count', 'helpful_count', 'not_helpful_count',
            'published_at',
        )[:200]))

    def create(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response({'detail': 'staff only'}, status=403)
        obj = HelpArticle.objects.create(
            slug=request.data.get('slug', '')[:160],
            title=request.data.get('title', '')[:255],
            body=request.data.get('body', ''),
            category=request.data.get('category', 'general')[:80],
            language=request.data.get('language', 'pt-AO'),
            related_issue_types=request.data.get('related_issue_types') or [],
            author=request.user,
        )
        return Response({'article_id': str(obj.id),
                         'slug': obj.slug}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def help_article_publish(request):
    article = get_object_or_404(HelpArticle, pk=request.data.get('article_id'))
    services.publish_help_article(article, editor=request.user)
    return Response({'status': article.status})


# ─── CH3 — Tickets ────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ticket_create(request):
    ticket = services.create_ticket(
        requester=request.user,
        subject=request.data.get('subject', ''),
        description=request.data.get('description', ''),
        channel_code=request.data.get('channel_code', ''),
        issue_type=request.data.get('issue_type', 'other'),
        related_order_id=request.data.get('related_order_id', ''),
        related_product_id=request.data.get('related_product_id', ''),
        language=request.data.get('language', 'pt-AO'),
        country=request.data.get('country', ''),
        priority=int(request.data.get('priority', 3)),
        on_behalf_of=request.data.get('on_behalf_of', 'buyer'),
    )
    return Response({'ticket_id': str(ticket.id),
                     'ticket_number': ticket.ticket_number,
                     'status': ticket.status,
                     'priority': ticket.priority}, status=201)


class MyTicketsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = SupportTicket.objects.filter(
            requester=request.user,
        ).values('id', 'ticket_number', 'subject', 'status',
                 'priority', 'issue_type', 'created_at',
                 'first_response_due_at', 'resolution_due_at',
                 'resolved_at')[:200]
        return Response(list(rows))


class TicketDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):
        ticket = get_object_or_404(SupportTicket, pk=ticket_id)
        if (ticket.requester_id != request.user.id
                and not request.user.is_staff):
            return Response({'detail': 'forbidden'}, status=403)
        msgs = ticket.messages.values(
            'id', 'author_id', 'author_kind', 'body',
            'is_internal_note', 'sent_at',
        )[:200]
        return Response({
            'id': str(ticket.id),
            'ticket_number': ticket.ticket_number,
            'subject': ticket.subject,
            'description': ticket.description,
            'status': ticket.status,
            'priority': ticket.priority,
            'issue_type': ticket.issue_type,
            'assigned_to_id': ticket.assigned_to_id,
            'first_response_due_at': ticket.first_response_due_at and ticket.first_response_due_at.isoformat(),
            'resolution_due_at': ticket.resolution_due_at and ticket.resolution_due_at.isoformat(),
            'created_at': ticket.created_at.isoformat(),
            'messages': list(msgs),
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ticket_reply(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    if (ticket.requester_id != request.user.id
            and not request.user.is_staff):
        return Response({'detail': 'forbidden'}, status=403)
    kind = 'agent' if request.user.is_staff else 'buyer'
    msg = services.reply_to_ticket(
        ticket=ticket, author=request.user,
        body=request.data.get('body', ''),
        author_kind=kind,
        is_internal_note=bool(request.data.get('is_internal_note', False)),
        attachments=request.data.get('attachments') or [],
    )
    return Response({'message_id': msg.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def ticket_assign(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    agent = get_object_or_404(User, pk=request.data.get('agent_id'))
    services.assign_ticket(ticket, agent=agent)
    return Response({'status': ticket.status,
                     'assigned_to_id': ticket.assigned_to_id})


@api_view(['POST'])
@permission_classes([IsAdmin])
def ticket_resolve(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    services.resolve_ticket(ticket, agent=request.user,
                              resolution_summary=request.data.get('resolution_summary', ''))
    return Response({'status': ticket.status,
                     'resolved_at': ticket.resolved_at.isoformat()})


@api_view(['POST'])
@permission_classes([IsAdmin])
def ticket_close(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    services.close_ticket(ticket, actor=request.user)
    return Response({'status': ticket.status})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ticket_reopen(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    services.reopen_ticket(ticket, actor=request.user,
                              reason=request.data.get('reason', ''))
    return Response({'status': ticket.status,
                     'reopened_count': ticket.reopened_count})


# ─── CH6 — Agent capability check ─────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def agent_can_check(request):
    return Response(services.agent_can(
        role_code=request.data.get('role_code', ''),
        action_code=request.data.get('action_code', ''),
        amount=Decimal(str(request.data.get('amount'))) if request.data.get('amount') else None,
    ))


# ─── CH7 — Live chat queue ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chat_queue_join(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    q = services.join_chat_queue(
        ticket=ticket,
        channel_code=request.data.get('channel_code', 'live_chat'),
        language=request.data.get('language', 'pt-AO'),
        requested_skills=request.data.get('requested_skills') or [],
    )
    return Response({'queue_id': str(q.id),
                     'position': q.queue_position,
                     'estimated_wait_seconds': q.estimated_wait_seconds},
                    status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def chat_queue_assign(request):
    q = get_object_or_404(ChatQueue, pk=request.data.get('queue_id'))
    agent = get_object_or_404(User, pk=request.data.get('agent_id'))
    ok = services.assign_chat_from_queue(q, agent=agent)
    return Response({'ok': ok, 'status': q.status})


@api_view(['POST'])
@permission_classes([IsAdmin])
def chat_queue_transfer(request):
    q = get_object_or_404(ChatQueue, pk=request.data.get('queue_id'))
    to_agent = get_object_or_404(User, pk=request.data.get('to_agent_id'))
    services.transfer_chat(q, from_agent=request.user, to_agent=to_agent,
                              reason=request.data.get('reason', ''))
    return Response({'ok': True}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def chat_queue_end(request):
    q = get_object_or_404(ChatQueue, pk=request.data.get('queue_id'))
    services.end_chat(q)
    return Response({'status': q.status})


# ─── CH8 — Chatbot ───────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chatbot_start(request):
    c = services.start_chatbot_conversation(user=request.user)
    return Response({'conversation_id': str(c.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chatbot_turn(request):
    conv = get_object_or_404(ChatbotConversation,
                              pk=request.data.get('conversation_id'),
                              user=request.user)
    return Response(services.append_chatbot_turn(
        conversation=conv,
        utterance=request.data.get('utterance', ''),
    ))


# ─── CH9 — CSAT ───────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def csat_submit(request):
    try:
        resp = services.submit_csat(
            survey_token=request.data.get('token', ''),
            score=int(request.data.get('score', 0)),
            comment=request.data.get('comment', ''),
            nps_score=int(request.data['nps_score']) if request.data.get('nps_score') is not None else None,
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'response_id': resp.pk, 'sentiment': resp.sentiment},
                    status=201)


# ─── CH10 — Escalation ───────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def escalation_trigger(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    case = services.trigger_escalation(
        ticket=ticket,
        trigger_kind=request.data.get('trigger_kind', 'manual_request'),
        rule_code=request.data.get('rule_code', ''),
    )
    if not case:
        return Response({'detail': 'no matching rule'}, status=404)
    return Response({'case_id': str(case.id),
                     'target_tier': case.target_tier_id},
                    status=201)


# ─── CH11 — Refund authorisation ─────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def refund_authorise(request):
    return Response(services.authorise_refund(
        role_code=request.data.get('role_code', ''),
        category=request.data.get('category', ''),
        amount=Decimal(str(request.data.get('amount', 0))),
        currency=request.data.get('currency', 'AOA'),
    ))


# ─── CH12 — Compensation grant ───────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def compensation_grant(request):
    ticket = None
    if request.data.get('ticket_id'):
        ticket = SupportTicket.objects.filter(pk=request.data['ticket_id']).first()
    try:
        grant = services.grant_compensation(
            ticket=ticket,
            rule_code=request.data.get('rule_code', ''),
            actor=request.user,
            override_amount=Decimal(str(request.data['override_amount'])) if request.data.get('override_amount') else None,
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'grant_id': str(grant.id),
                     'delivered_reference': grant.delivered_reference,
                     'amount': str(grant.amount)}, status=201)


# ─── CH13 — Smart suggestions ────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def smart_suggest(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    rows = services.surface_smart_suggestions(ticket, max_n=int(request.data.get('max_n', 5)))
    return Response({'suggestions': [
        {'article_id': str(s.article_id), 'relevance': s.relevance_score,
         'title': s.article.title}
        for s in rows
    ]})


# ─── CH14 — Phone ────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def phone_call_start(request):
    call = services.start_phone_call(
        caller_number=request.data.get('caller_number', ''),
        ivr_flow_code=request.data.get('ivr_flow_code', ''),
    )
    return Response({'call_id': str(call.id),
                     'status': call.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def phone_call_end(request):
    call = get_object_or_404(PhoneCall, pk=request.data.get('call_id'))
    services.end_phone_call(call, status=request.data.get('status', 'completed'))
    return Response({'status': call.status,
                     'duration_seconds': call.duration_seconds})


# ─── CH16 — Trust & safety report ────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ts_report_file(request):
    ticket = None
    if request.data.get('ticket_id'):
        ticket = SupportTicket.objects.filter(pk=request.data['ticket_id']).first()
    subject = None
    if request.data.get('subject_user_id'):
        subject = User.objects.filter(pk=request.data['subject_user_id']).first()
    obj = services.file_trust_safety_report(
        reporter=request.user, ticket=ticket, subject_user=subject,
        subject_product_id=request.data.get('subject_product_id', ''),
        category=request.data.get('category', 'other'),
        severity=int(request.data.get('severity', 5)),
        description=request.data.get('description', ''),
        evidence_keys=request.data.get('evidence_keys') or [],
    )
    return Response({'report_id': str(obj.id),
                     'status': obj.status}, status=201)


# ─── CH17 — Proactive outreach ───────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def proactive_outreach_send(request):
    user = get_object_or_404(User, pk=request.data.get('recipient_id'))
    try:
        obj = services.proactive_outreach(
            trigger_code=request.data.get('trigger_code', ''),
            recipient=user,
            related_order_id=request.data.get('related_order_id', ''),
            payload=request.data.get('payload') or {},
            channel=request.data.get('channel', 'push'),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'outreach_id': obj.pk}, status=201)


# ─── CH19 — Translation ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def translate(request):
    return Response(services.translate_text(
        source_text=request.data.get('source_text', ''),
        source_lang=request.data.get('source_lang', 'pt-AO'),
        target_lang=request.data.get('target_lang', 'en-US'),
    ))


# ─── CH18 — Workforce schedule ───────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def shift_plan(request):
    from datetime import date
    schedule_date = date.fromisoformat(request.data.get('schedule_date'))
    obj = services.plan_shift_schedule(
        schedule_date=schedule_date,
        forecasted_volume=int(request.data.get('forecasted_volume', 0)),
        target_handle_seconds=int(request.data.get('target_handle_seconds', 480)),
    )
    return Response({'required_headcount': obj.required_headcount}, status=201)


# ─── CH21 — QA audit ─────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def qa_audit_record(request):
    ticket = get_object_or_404(SupportTicket, pk=request.data.get('ticket_id'))
    if not ticket.assigned_to:
        return Response({'detail': 'ticket has no agent'}, status=422)
    accuracy = int(request.data.get('accuracy_score', 0))
    empathy = int(request.data.get('empathy_score', 0))
    timeliness = int(request.data.get('timeliness_score', 0))
    compliance = int(request.data.get('compliance_score', 0))
    overall = int(round((accuracy + empathy + timeliness + compliance) / 4))
    obj = QaAuditScore.objects.create(
        ticket=ticket, auditor=request.user,
        agent=ticket.assigned_to,
        accuracy_score=accuracy, empathy_score=empathy,
        timeliness_score=timeliness, compliance_score=compliance,
        overall_score=overall,
        coaching_notes=request.data.get('coaching_notes', ''),
    )
    return Response({'audit_id': obj.pk, 'overall_score': overall},
                    status=201)


# ─── CH24 — KPI ──────────────────────────────────────────────

class CsOpsKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = CsOpsKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_cs_ops_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'tickets_created': snap.tickets_created,
            'tickets_resolved': snap.tickets_resolved,
            'backlog_count': snap.backlog_count,
            'avg_first_response_minutes': snap.avg_first_response_minutes,
            'avg_resolution_minutes': snap.avg_resolution_minutes,
            'sla_compliance_pct': snap.sla_compliance_pct,
            'csat_avg': snap.csat_avg,
            'first_contact_resolution_pct': snap.first_contact_resolution_pct,
            'escalation_rate_pct': snap.escalation_rate_pct,
            'chat_abandon_pct': snap.chat_abandon_pct,
            'chatbot_deflection_pct': snap.chatbot_deflection_pct,
            'compensation_count': snap.compensation_count,
            'compensation_amount': str(snap.compensation_amount),
            'by_issue_type': snap.by_issue_type,
        })
