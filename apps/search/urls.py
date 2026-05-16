from django.urls import path
from .views import (
    SearchView, SearchSuggestionsView, TrendingView,
    SearchEventView, SearchEventBatchView,
)


urlpatterns = [
    path("", SearchView.as_view(), name="search"),
    path("suggestions/", SearchSuggestionsView.as_view(), name="suggestions"),
    path("trending/", TrendingView.as_view(), name="trending"),
    path("event/", SearchEventView.as_view(), name="search-event"),
    path("event/batch/", SearchEventBatchView.as_view(), name="search-event-batch"),
]
