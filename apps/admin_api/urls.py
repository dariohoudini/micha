"""
apps/admin_api/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.AdminDashboardStatsView.as_view()),
    path('users/', views.AdminUsersListView.as_view()),
    path('users/<uuid:user_id>/action/', views.AdminUserActionView.as_view()),
    path('orders/', views.AdminOrdersListView.as_view()),
    path('orders/<uuid:order_id>/resolve/', views.AdminOrderDisputeView.as_view()),
    path('sellers/', views.AdminSellersListView.as_view()),
    path('products/', views.AdminProductsListView.as_view()),
    path('products/<uuid:product_id>/action/', views.AdminProductActionView.as_view()),
    path('revenue/', views.AdminRevenueChartView.as_view()),
]
