from django.urls import path
from .views import ConversationListCreateView, MessageListCreateView

app_name = "chat"

urlpatterns = [
    # Conversations
    path("conversations/", ConversationListCreateView.as_view(), name="conversation-list-create"),

    # Messages in a conversation
    path(
        "conversations/<int:conversation_id>/messages/",
        MessageListCreateView.as_view(),
        name="message-list-create",
    ),
]
