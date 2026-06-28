from django.urls import path

from .views import MyIntentsView, charge_view, webhook_view

urlpatterns = [
    path('charge/', charge_view, name='pg-charge'),
    path('intents/me/', MyIntentsView.as_view(), name='pg-intents-me'),
    path('webhooks/<str:gateway>/', webhook_view, name='pg-webhook'),
]
