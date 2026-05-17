from django.urls import path
from .views import ClickView, MyAffiliateView, MyConversionsView, MyPayoutsView

urlpatterns = [
    path('click/', ClickView.as_view(), name='affiliates-click'),
    path('me/', MyAffiliateView.as_view(), name='affiliates-me'),
    path('me/conversions/', MyConversionsView.as_view(), name='affiliates-conversions'),
    path('me/payouts/', MyPayoutsView.as_view(), name='affiliates-payouts'),
]
