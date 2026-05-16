from django.urls import path
from .views import RecommendationListView, RecommendationDetailView, ForecastDetailView

urlpatterns = [
    path('recommendations/', RecommendationListView.as_view(), name='forecasting-recs'),
    path('recommendations/<int:pk>/', RecommendationDetailView.as_view(), name='forecasting-rec-detail'),
    path('products/<int:product_id>/', ForecastDetailView.as_view(), name='forecasting-product'),
]
