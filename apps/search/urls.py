from django.urls import path
from .views import SearchView, SearchSuggestionsView, TrendingView


urlpatterns = [
    path("", SearchView.as_view(), name="search"),
    path("suggestions/", SearchSuggestionsView.as_view(), name="suggestions"),
    path("trending/", TrendingView.as_view(), name="trending"),
]
