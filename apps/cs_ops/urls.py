from django.urls import path

from .views import (
    CsOpsKpiView, HelpArticleListCreateView, MyTicketsView,
    TicketDetailView, agent_can_check, chat_queue_assign,
    chat_queue_end, chat_queue_join, chat_queue_transfer,
    chatbot_start, chatbot_turn, compensation_grant, csat_submit,
    escalation_trigger, help_article_publish, phone_call_end,
    phone_call_start, proactive_outreach_send, qa_audit_record,
    refund_authorise, shift_plan, smart_suggest, ticket_assign,
    ticket_close, ticket_create, ticket_reopen, ticket_reply,
    ticket_resolve, translate, ts_report_file,
)


urlpatterns = [
    # CH2 — help articles
    path('help/articles/',                HelpArticleListCreateView.as_view(), name='cs-help'),
    path('help/articles/publish/',        help_article_publish, name='cs-help-publish'),
    # CH3 — tickets
    path('tickets/',                      ticket_create, name='cs-ticket-create'),
    path('tickets/me/',                   MyTicketsView.as_view(), name='cs-tickets-me'),
    path('tickets/<uuid:ticket_id>/',     TicketDetailView.as_view(), name='cs-ticket-detail'),
    path('tickets/reply/',                ticket_reply, name='cs-ticket-reply'),
    path('tickets/assign/',               ticket_assign, name='cs-ticket-assign'),
    path('tickets/resolve/',              ticket_resolve, name='cs-ticket-resolve'),
    path('tickets/close/',                ticket_close, name='cs-ticket-close'),
    path('tickets/reopen/',               ticket_reopen, name='cs-ticket-reopen'),
    # CH6 — agent capability
    path('agents/can/',                   agent_can_check, name='cs-agent-can'),
    # CH7 — chat queue
    path('chat/queue/join/',              chat_queue_join, name='cs-chat-join'),
    path('chat/queue/assign/',            chat_queue_assign, name='cs-chat-assign'),
    path('chat/queue/transfer/',          chat_queue_transfer, name='cs-chat-transfer'),
    path('chat/queue/end/',               chat_queue_end, name='cs-chat-end'),
    # CH8 — chatbot
    path('chatbot/conversations/',        chatbot_start, name='cs-bot-start'),
    path('chatbot/turn/',                 chatbot_turn, name='cs-bot-turn'),
    # CH9 — CSAT
    path('csat/submit/',                  csat_submit, name='cs-csat-submit'),
    # CH10 — escalation
    path('escalations/trigger/',          escalation_trigger, name='cs-escalate'),
    # CH11 — refund authorisation
    path('refund/authorise/',             refund_authorise, name='cs-refund-auth'),
    # CH12 — compensation grant
    path('compensation/grant/',           compensation_grant, name='cs-comp-grant'),
    # CH13 — smart suggestions
    path('kb/smart-suggest/',             smart_suggest, name='cs-smart-suggest'),
    # CH14 — phone
    path('phone/calls/start/',            phone_call_start, name='cs-call-start'),
    path('phone/calls/end/',              phone_call_end, name='cs-call-end'),
    # CH16 — trust & safety
    path('trust-safety/report/',          ts_report_file, name='cs-ts-report'),
    # CH17 — proactive outreach
    path('proactive/send/',               proactive_outreach_send, name='cs-proactive'),
    # CH19 — translate
    path('translate/',                    translate, name='cs-translate'),
    # CH18 — workforce schedule
    path('shifts/plan/',                  shift_plan, name='cs-shift-plan'),
    # CH21 — QA audit
    path('qa/audit/',                     qa_audit_record, name='cs-qa-audit'),
    # CH24 — KPI
    path('admin/kpi/',                    CsOpsKpiView.as_view(), name='cs-kpi'),
]
