from django.urls import path
from .views import (
    HomepageFeedView,
    PersonalisedFeedView,
    TrackInteractionView,
    StockUrgencyView,
    UserInterestView,
    PriceAlertView,
    BackInStockView,
    RecentlyViewedView,
    FrequentlyBoughtTogetherView,
)


urlpatterns = [
    path("homepage/", HomepageFeedView.as_view(), name="homepage"),
    path("feed/", PersonalisedFeedView.as_view(), name="feed"),
    path("track/", TrackInteractionView.as_view(), name="track"),
    path("viewing/<int:product_id>/", StockUrgencyView.as_view(), name="viewing"),
    path("interests/", UserInterestView.as_view(), name="interests"),
    path("price-alerts/", PriceAlertView.as_view(), name="price-alerts"),
    path("back-in-stock/", BackInStockView.as_view(), name="back-in-stock"),
    path("recently-viewed/", RecentlyViewedView.as_view(), name="recently-viewed"),
    path("frequently-bought/<int:product_id>/", FrequentlyBoughtTogetherView.as_view(), name="frequently-bought"),
]
