from django.urls import path
from .views import (
    ReviewCreateView,
    SellerReviewListView,
    SellerRatingView,
    ReviewUpdateDeleteView,
    ProductReviewCreateView,
    ProductReviewListView,
    ProductRatingView,
    SellerReplyView,
    VoteReviewHelpfulView,
)


urlpatterns = [
    # Seller reviews
    path('create/', ReviewCreateView.as_view(), name='review-create'),
    path('<int:pk>/', ReviewUpdateDeleteView.as_view(), name='review-detail'),
    path('seller/<int:seller_id>/', SellerReviewListView.as_view(), name='seller-reviews'),
    path('seller/<int:seller_id>/rating/', SellerRatingView.as_view(), name='seller-rating'),

    # Product reviews
    path('product/', ProductReviewCreateView.as_view(), name='product-review-create'),
    path('product/<int:product_id>/', ProductReviewListView.as_view(), name='product-reviews'),
    path('product/<int:product_id>/rating/', ProductRatingView.as_view(), name='product-rating'),
    path('product/<int:review_id>/reply/', SellerReplyView.as_view(), name='seller-reply'),
    path('product/<int:review_id>/helpful/', VoteReviewHelpfulView.as_view(), name='helpful-vote'),
]
