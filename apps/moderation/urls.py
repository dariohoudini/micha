"""
URL routes for apps/moderation.

Legacy paths kept for back-compat:
  flags/                            list of unresolved flags
  flags/<pk>/resolve/               mark a flag resolved (no escalation)

R4 moderator queue:
  queue/                            paginated + filtered queue
  queue/<pk>/approve/               dismiss the flag
  queue/<pk>/reject/                remove content + run escalation
  queue/<pk>/escalate/              kick to senior review

Other:
  ip-bans/                          list / create IP bans
  buyer-protection/                 file a buyer-protection claim
"""
from django.urls import path
from .views import (
    BuyerProtectionView,
    ContentFlagListView,
    IPBanView,
    ModerationApproveView,
    ModerationEscalateView,
    ModerationQueueView,
    ModerationRejectView,
    ResolveContentFlagView,
)

urlpatterns = [
    # Legacy
    path("flags/", ContentFlagListView.as_view()),
    path("flags/<int:pk>/resolve/", ResolveContentFlagView.as_view()),

    # R4: moderator queue
    path("queue/", ModerationQueueView.as_view(), name="moderation-queue"),
    path("queue/<int:pk>/approve/", ModerationApproveView.as_view(),
         name="moderation-queue-approve"),
    path("queue/<int:pk>/reject/", ModerationRejectView.as_view(),
         name="moderation-queue-reject"),
    path("queue/<int:pk>/escalate/", ModerationEscalateView.as_view(),
         name="moderation-queue-escalate"),

    # IP bans + buyer protection
    path("ip-bans/", IPBanView.as_view()),
    path("buyer-protection/", BuyerProtectionView.as_view()),
]
