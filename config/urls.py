from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.seo.views import HealthCheckView, robots_txt, sitemap_xml

ADMIN_URL = getattr(settings, "ADMIN_URL", "admin/")

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap"),

    path("api/v1/auth/",            include("apps.users.urls")),
    path("api/v1/verification/",    include("apps.verification.urls")),
    path("api/v1/stores/",          include("apps.stores.urls")),
    path("api/v1/products/",        include("apps.products.urls")),
    path("api/v1/listings/",        include("apps.listings.urls")),
    path("api/v1/search/",          include("apps.search.urls")),
    path("api/v1/recommendations/", include("apps.recommendations.urls")),
    path("api/v1/collections/",     include("apps.collections.urls")),
    path("api/v1/seo/",             include("apps.seo.urls")),
    path("api/v1/cart/",            include("apps.cart.urls")),
    path("api/v1/wishlist/",        include("apps.wishlist.urls")),
    path("api/v1/orders/",          include("apps.orders.urls")),
    path("api/v1/shipping/",        include("apps.shipping.urls")),
    path("api/v1/promotions/",      include("apps.promotions.urls")),
    path("api/v1/payments/",        include("apps.payments.urls")),
    path("api/v1/chat/",            include("apps.chat.urls")),
    path("api/v1/notifications/",   include("apps.notifications.urls")),
    path("api/v1/accounts/",        include("apps.accounts.urls")),
    path("api/v1/reviews/",         include("apps.reviews.urls")),
    path("api/v1/reports/",         include("apps.reports.urls")),
    path("api/v1/seller/",          include("apps.seller.urls")),
    path("api/v1/inventory/",       include("apps.inventory.urls")),
    path("api/v1/analytics/",       include("apps.analytics.urls")),
    path("api/v1/admin-actions/",   include("apps.admin_actions.urls")),
    path("api/v1/trust/",           include("apps.trust.urls")),
    path("api/v1/ai/",              include("apps.ai_engine.urls")),
    path("api/v1/admin-api/",       include("apps.admin_api.urls")),

    # Legacy /api/ aliases — same includes, no duplicate namespace issue
    path("api/auth/",               include("apps.users.urls")),
    path("api/stores/",             include("apps.stores.urls")),
    path("api/products/",           include("apps.products.urls")),
    path("api/cart/",               include("apps.cart.urls")),
    path("api/wishlist/",           include("apps.wishlist.urls")),
    path("api/orders/",             include("apps.orders.urls")),
    path("api/payments/",           include("apps.payments.urls")),
    path("api/reviews/",            include("apps.reviews.urls")),
    path("api/notifications/",      include("apps.notifications.urls")),
    path("api/search/",             include("apps.search.urls")),
    path("api/trust/",              include("apps.trust.urls")),
    path("api/ai/",                 include("apps.ai_engine.urls")),
    path("api/admin/",              include("apps.admin_api.urls")),
    path("api/rentals/",            include("apps.rentals.urls")),
    path("api/verification-gate/",  include("apps.verification_gate.urls")),
]

try:
    urlpatterns.append(path("api/v1/i18n/", include("apps.i18n.urls")))
except Exception:
    pass

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
