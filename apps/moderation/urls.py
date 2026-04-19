
from django.urls import path
from .views import *
urlpatterns = [
    path("flags/", ContentFlagListView.as_view()),
    path("flags/<int:pk>/resolve/", ResolveContentFlagView.as_view()),
    path("ip-bans/", IPBanView.as_view()),
    path("buyer-protection/", BuyerProtectionView.as_view()),
]
