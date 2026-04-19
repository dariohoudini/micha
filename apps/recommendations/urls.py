from django.urls import path
from .views import (
    HomepageFeedView,
    PersonalisedFeedView,
    TrackInteractionView,
    StockUrgencyView,
    UserInterestView,
    PriceAlertView,
    BackInStockView,
)


urlpatterns = [
    path("homepage/", HomepageFeedView.as_view(), name="homepage"),
    path("feed/", PersonalisedFeedView.as_view(), name="feed"),
    path("track/", TrackInteractionView.as_view(), name="track"),
    path("viewing/<int:product_id>/", StockUrgencyView.as_view(), name="viewing"),
    path("interests/", UserInterestView.as_view(), name="interests"),
    path("price-alerts/", PriceAlertView.as_view(), name="price-alerts"),
    path("back-in-stock/", BackInStockView.as_view(), name="back-in-stock"),
]
