from django.urls import path
from .views import AdminActionCreateView

urlpatterns = [
    path("action/", AdminActionCreateView.as_view(), name="admin-action"),
]
