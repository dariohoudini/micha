"""
apps/admin_api/urls.py
"""
from django.urls import path
from . import inspector, views

urlpatterns = [
    path('stats/', views.AdminDashboardStatsView.as_view()),
    path('users/', views.AdminUsersListView.as_view()),
    # User & Product PKs are BigAutoField (int); Order PK is UUID. The int
    # routes were declared <uuid:...> so admin user/product actions 404'd.
    path('users/<int:user_id>/action/', views.AdminUserActionView.as_view()),
    # Admin User Management doc CH8-12/CH20.1 — the inspector panel +
    # security actions. The inspector READ is itself audited.
    path('users/<int:user_id>/inspector/',
         inspector.AdminUserInspectorView.as_view()),
    path('users/<int:user_id>/sessions/terminate/',
         inspector.AdminUserTerminateSessionsView.as_view()),
    path('users/<int:user_id>/password-reset/',
         inspector.AdminUserPasswordResetView.as_view()),
    path('orders/', views.AdminOrdersListView.as_view()),
    path('orders/<uuid:order_id>/resolve/', views.AdminOrderDisputeView.as_view()),
    path('sellers/', views.AdminSellersListView.as_view()),
    path('products/', views.AdminProductsListView.as_view()),
    path('products/<int:product_id>/action/', views.AdminProductActionView.as_view()),
    path('revenue/', views.AdminRevenueChartView.as_view()),
    path('ops-queue/', views.OpsQueueView.as_view()),
    path('ops-queue/<str:kind>/<int:item_id>/action/', views.OpsQueueActionView.as_view()),
]
