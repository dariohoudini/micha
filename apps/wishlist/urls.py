from django.urls import path
from .views import WishlistView, AddToWishlistView, RemoveFromWishlistView, ClearWishlistView


urlpatterns = [
    path('', WishlistView.as_view(), name='wishlist'),
    path('add/', AddToWishlistView.as_view(), name='add-to-wishlist'),
    path('items/<int:item_id>/', RemoveFromWishlistView.as_view(), name='remove-wishlist-item'),
    path('clear/', ClearWishlistView.as_view(), name='clear-wishlist'),
]
