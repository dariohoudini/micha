from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.seo.views import HealthCheckView, robots_txt, sitemap_xml
from apps.seo.well_known import apple_app_site_association, assetlinks_json
from apps.monitoring.health import healthz, readyz, build_info

ADMIN_URL = getattr(settings, "ADMIN_URL", "admin/")

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    # Split liveness vs readiness — see apps/monitoring/health.py.
    # /health/ kept as legacy alias for existing callers.
    #   /health/live  + /health/ready  — canonical paths the Hosting &
    #   Deployment spec (CH8 Dockerfile HEALTHCHECK, CH11 nginx /health/*,
    #   Part 2 readiness probe) expects. Aliased to the same liveness /
    #   readiness handlers so the container + load-balancer probes work
    #   exactly as specified. /healthz + /readyz kept for existing callers.
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("health/live", healthz, name="health-live"),
    path("health/ready", readyz, name="health-ready"),
    path("health/", HealthCheckView.as_view(), name="health"),
    # CI/CD & VC doc CH13/CH20 — "what version is live?" must always be
    # answerable. Stamped by the build pipeline (commit SHA / version /
    # build time), surfaced here for incident response + deploy traceability.
    path("version", build_info, name="build-info"),
    path("metrics", include("apps.telemetry.urls")),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap"),

    # R5-C: native deep-link verification files. MUST be at the
    # domain root (Apple/Google ignore them under any prefix). No
    # auth, no CSRF — they're public verification metadata, fetched
    # by Apple's CDN and Google's Play Services.
    path(".well-known/apple-app-site-association",
         apple_app_site_association, name="aasa"),
    path(".well-known/assetlinks.json",
         assetlinks_json, name="assetlinks"),
    # R7: server-rendered product page shells for SEO (Googlebot,
    # social-share previews). Humans get JS-redirected to the SPA;
    # crawlers see <title>/<meta>/JSON-LD without executing JS.
    path("p/<slug:slug>/",
         __import__('apps.seo.prerender', fromlist=['render_product_seo']).render_product_seo,
         name="seo-product"),

    path("api/v1/auth/",            include("apps.users.urls")),
    path("api/v1/verification/",    include("apps.verification.urls")),
    path("api/v1/stores/",          include("apps.stores.urls")),
    path("api/v1/products/",        include("apps.products.urls")),
    path("api/v1/",                 include("apps.onboarding.urls")),
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
    path("api/v1/account/data-request/", include("apps.data_rights.urls")),
    path("api/v1/flags/",           include("apps.flags.urls")),
    path("api/v1/fx/",              include("apps.fx.urls")),
    path("api/v1/admin-api/bulk/",  include("apps.bulk_ops.urls")),
    path("api/v1/dev/keys/",        include("apps.dev_keys.urls")),
    path("api/v1/tax/",             include("apps.tax.urls")),
    path("api/v1/admin-api/cases/", include("apps.cases.urls")),
    path("api/v1/loyalty/",         include("apps.loyalty.urls")),
    path("api/v1/2fa/",             include("apps.two_factor.urls")),
    path("api/v1/alerts/",          include("apps.alerts.urls")),
    path("api/v1/forecasting/",     include("apps.forecasting.urls")),
    path("api/v1/feed/",            include("apps.feed.urls")),
    path("api/v1/affiliates/",      include("apps.affiliates.urls")),
    path("api/v1/gift-cards/",      include("apps.gift_cards.urls")),
    path("api/v1/waitlist/",        include("apps.waitlist.urls")),
    path("api/v1/reviews/",         include("apps.reviews.urls")),
    path("api/v1/reports/",         include("apps.reports.urls")),
    path("api/v1/seller/",          include("apps.seller.urls")),
    path("api/v1/seller-onboarding/", include("apps.seller_onboarding.urls")),
    path("api/v1/buyer-engagement/",  include("apps.buyer_engagement.urls")),
    path("api/v1/payment-gateways/",  include("apps.payment_gateways.urls")),
    path("api/v1/fraud-engine/",      include("apps.fraud_engine.urls")),
    path("api/v1/marketing-engine/",  include("apps.marketing_engine.urls")),
    path("api/v1/pricing-inventory/", include("apps.pricing_inventory.urls")),
    path("api/v1/logistics-ops/",     include("apps.logistics_ops.urls")),
    path("api/v1/payment-ops/",       include("apps.payment_ops.urls")),
    path("api/v1/cs-ops/",            include("apps.cs_ops.urls")),
    path("api/v1/trust-safety/",      include("apps.trust_safety.urls")),
    path("api/v1/search-discovery/",  include("apps.search_discovery.urls")),
    path("api/v1/data-analytics/",    include("apps.data_analytics.urls")),
    path("api/v1/mobile/",            include("apps.mobile_app.urls")),
    path("api/v1/seller-tools/",      include("apps.seller_tools.urls")),
    path("api/v1/admin-console/",     include("apps.admin_console.urls")),
    path("api/v1/payments-ao/",       include("apps.payments_angola.urls")),
    path("api/v1/accounting/",        include("apps.accounting.urls")),
    path("api/v1/stock/",             include("apps.stock_engine.urls")),
    path("api/v1/last-mile/",         include("apps.last_mile.urls")),
    path("api/v1/buyer-experience/",  include("apps.buyer_experience.urls")),
    path("api/v1/seller-operations/", include("apps.seller_operations.urls")),
    path("api/v1/inventory/",       include("apps.inventory.urls")),
    path("api/v1/analytics/",       include("apps.analytics.urls")),
    path("api/v1/admin-actions/",   include("apps.admin_actions.urls")),
    path("api/v1/trust/",           include("apps.trust.urls")),
    path("api/v1/ai/",              include("apps.ai_engine.urls")),
    path("api/v1/rentals/",            include("apps.rentals.urls")),
    path("api/v1/verification-gate/",  include("apps.verification_gate.urls")),
    path("api/v1/disputes/",           include("apps.disputes.urls")),
    path("api/v1/moderation/",         include("apps.moderation.urls")),
    path("api/v1/security/",     include("apps.security.urls")),
    path("api/v1/monitoring/",   include("apps.monitoring.urls")),
    path("api/v1/admin-api/",    include("apps.admin_api.urls")),
    path("api/v1/admin/outbox/", include("apps.outbox.urls")),
    path("api/v1/admin/ledger/", include("apps.ledger.urls")),
    path("api/v1/admin/inbound-webhooks/", include("apps.inbound_webhooks.urls")),
    path("api/v1/admin/outbound-webhooks/", include("apps.webhooks.admin_urls")),
    path("api/v1/webhooks/", include("apps.webhooks.urls")),

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
