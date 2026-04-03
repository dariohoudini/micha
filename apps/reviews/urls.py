from django.urls import path
from .views import ReviewCreateView, SellerReviewListView

app_name = "reviews"

urlpatterns = [
    path("create/", ReviewCreateView.as_view(), name="review-create"),
    path(
        "seller/<int:seller_id>/",
        SellerReviewListView.as_view(),
        name="seller-reviews",
        
    ),
    
]
