from django.urls import path
from .views import (
    CartView, AddToCartView, UpdateCartItemView,
    RemoveCartItemView, ClearCartView, MoveWishlistToCartView,
)


urlpatterns = [
    path('', CartView.as_view(), name='cart'),
    path('add/', AddToCartView.as_view(), name='add-to-cart'),
    path('items/<int:item_id>/', UpdateCartItemView.as_view(), name='update-cart-item'),
    path('items/<int:item_id>/remove/', RemoveCartItemView.as_view(), name='remove-cart-item'),
    path('clear/', ClearCartView.as_view(), name='clear-cart'),
    path('from-wishlist/<int:item_id>/', MoveWishlistToCartView.as_view(), name='wishlist-to-cart'),
]
