
from django.urls import path
from .views import *
urlpatterns = [
    path("open/", OpenDisputeView.as_view()),
    path("my/", MyDisputesView.as_view()),
    path("<uuid:pk>/", DisputeDetailView.as_view()),
    path("<uuid:pk>/message/", DisputeMessageView.as_view()),
    path("admin/", AdminDisputeListView.as_view()),
    path("admin/<uuid:pk>/resolve/", AdminResolveDisputeView.as_view()),
    path("fraud/", FraudFlagView.as_view()),
    path("fraud/<int:pk>/", FraudFlagView.as_view()),
]
