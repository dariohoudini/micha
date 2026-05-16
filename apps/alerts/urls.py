from django.urls import path
from .views import SavedSearchListView, SavedSearchDetailView, AlertDeliveryListView

urlpatterns = [
    path('saved-searches/', SavedSearchListView.as_view(), name='alerts-saved-list'),
    path('saved-searches/<int:pk>/', SavedSearchDetailView.as_view(), name='alerts-saved-detail'),
    path('deliveries/', AlertDeliveryListView.as_view(), name='alerts-deliveries'),
]
