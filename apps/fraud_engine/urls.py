from django.urls import path

from .views import (
    AdminFraudDecisionsView, AdminIpReputationView, AdminRulesView,
    evaluate_view, register_device_view,
)

urlpatterns = [
    path('devices/register/', register_device_view, name='fe-register-device'),
    path('evaluate/', evaluate_view, name='fe-evaluate'),
    path('admin/decisions/', AdminFraudDecisionsView.as_view(), name='fe-decisions'),
    path('admin/rules/', AdminRulesView.as_view(), name='fe-rules'),
    path('admin/ip-reputation/', AdminIpReputationView.as_view(), name='fe-ips'),
]
