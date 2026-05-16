from django.urls import path
from .views import APIKeyListView, APIKeyDetailView, APIKeyRevokeView, APIKeyUsageView

urlpatterns = [
    path('', APIKeyListView.as_view(), name='dev-keys'),
    path('<int:pk>/', APIKeyDetailView.as_view(), name='dev-key-detail'),
    path('<int:pk>/revoke/', APIKeyRevokeView.as_view(), name='dev-key-revoke'),
    path('<int:pk>/usage/', APIKeyUsageView.as_view(), name='dev-key-usage'),
]
