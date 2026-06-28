
from django.urls import path
from .views import (
    OpenDisputeView,
    DisputeDetailView,
    DisputeMessageView,
    MyDisputesView,
    AdminDisputeListView,
    AdminResolveDisputeView,
    FraudFlagView,
)
urlpatterns = [
    path("open/", OpenDisputeView.as_view()),
    # User Process Flow §19 — Returns flow alias. Routes to the same
    # OpenDisputeView so a single atomic pipeline (evidence snapshot,
    # EarningsHold freeze, outbox publish) handles both intents.
    path("returns/", OpenDisputeView.as_view(), name="returns-open"),
    path("my/", MyDisputesView.as_view()),
    path("<uuid:pk>/", DisputeDetailView.as_view()),
    path("<uuid:pk>/message/", DisputeMessageView.as_view()),
    path("admin/", AdminDisputeListView.as_view()),
    path("admin/<uuid:pk>/resolve/", AdminResolveDisputeView.as_view()),
    path("fraud/", FraudFlagView.as_view()),
    path("fraud/<int:pk>/", FraudFlagView.as_view()),
]
