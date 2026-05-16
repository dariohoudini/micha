from django.urls import path
from .views import (
    StartSetupView, ConfirmSetupView, ChallengeView, StatusView,
    DisableView, RegenerateBackupCodesView, TrustedDevicesView,
)

urlpatterns = [
    path('status/', StatusView.as_view(), name='2fa-status'),
    path('setup/', StartSetupView.as_view(), name='2fa-setup'),
    path('confirm/', ConfirmSetupView.as_view(), name='2fa-confirm'),
    path('challenge/', ChallengeView.as_view(), name='2fa-challenge'),
    path('disable/', DisableView.as_view(), name='2fa-disable'),
    path('backup-codes/regenerate/', RegenerateBackupCodesView.as_view(), name='2fa-backup-regen'),
    path('devices/', TrustedDevicesView.as_view(), name='2fa-devices'),
]
