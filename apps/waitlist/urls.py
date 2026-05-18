from django.urls import path
from .views import WaitlistView, MyWaitlistView

urlpatterns = [
    path('me/', MyWaitlistView.as_view(), name='waitlist-me'),
    path('<int:product_id>/', WaitlistView.as_view(), name='waitlist-product'),
]
