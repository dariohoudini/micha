from django.urls import path
from .views import DataRequestView, DataRequestDetailView

urlpatterns = [
    path('', DataRequestView.as_view(), name='data-request-list'),
    path('<int:pk>/', DataRequestDetailView.as_view(), name='data-request-detail'),
]
