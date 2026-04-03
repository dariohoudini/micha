from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/auth/', include('apps.users.urls')),
    path('api/verification/', include('apps.verification.urls')),
    path('api/stores/', include('apps.stores.urls')),
    path('api/products/', include('apps.products.urls')),
    path('api/chat/', include('apps.chat.urls')),
    path('api/reviews/', include('apps.reviews.urls')),
    path('api/reports/', include('apps.reports.urls')),
    path('api/reports/', include('apps.reports.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/users/', include('apps.users.urls')),  # USERS endpoints
    path('api/reports/', include('apps.reports.urls')),  # 
    path('api/seller/', include('apps.seller.urls')),
    path("api/admin/", include("apps.admin_actions.urls")),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
