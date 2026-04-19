from django.urls import path
from .views import *
urlpatterns=[
    path('conversations/',ConversationListCreateView.as_view(),name='conversations'),
    path('conversations/<int:conversation_id>/messages/',MessageListCreateView.as_view(),name='messages'),
    path('conversations/<int:conversation_id>/read/',MarkReadView.as_view(),name='mark-read'),
    path('conversations/<int:conversation_id>/archive/',ArchiveChatView.as_view(),name='archive-chat'),
    path('conversations/<int:conversation_id>/report/',ReportConversationView.as_view(),name='report-chat'),
    path('quick-replies/',QuickReplyListCreateView.as_view(),name='quick-replies'),
]
