import logging
from django.http import HttpResponse
from django.utils import timezone
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

logger = logging.getLogger('micha')


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        checks = {}
        all_ok = True

        try:
            from django.db import connection
            connection.ensure_connection()
            connection.cursor().execute('SELECT 1')
            checks['database'] = 'ok'
        except Exception as e:
            checks['database'] = 'error'
            all_ok = False
            logger.error(f"Health DB failed: {e}")

        try:
            cache.set('_health', '1', timeout=5)
            assert cache.get('_health') == '1'
            cache.delete('_health')
            checks['cache'] = 'ok'
        except Exception:
            checks['cache'] = 'unavailable'

        try:
            from django.conf import settings
            import redis as redis_lib
            r = redis_lib.from_url(getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0'))
            r.ping()
            checks['celery_broker'] = 'ok'
        except Exception:
            checks['celery_broker'] = 'unavailable'

        try:
            from config.celery import app as celery_app
            i = celery_app.control.inspect(timeout=0.5)
            active = i.active()
            checks['celery_workers'] = f"{len(active)} worker(s)" if active else 'no workers'
        except Exception:
            checks['celery_workers'] = 'unavailable'

        return Response({
            'status': 'ok' if all_ok else 'degraded',
            'timestamp': timezone.now().isoformat(),
            'version': 'micha-api-v1',
            'checks': checks,
        }, status=200 if all_ok else 503)


def robots_txt(request):
    from django.conf import settings
    base = getattr(settings, 'FRONTEND_URL', 'https://micha.app')
    admin_url = getattr(settings, 'ADMIN_URL', 'admin/')
    lines = [
        'User-agent: *',
        'Allow: /api/products/',
        'Allow: /api/stores/',
        'Allow: /api/collections/',
        'Allow: /api/recommendations/homepage/',
        'Disallow: /api/auth/',
        'Disallow: /api/orders/',
        'Disallow: /api/payments/',
        'Disallow: /api/cart/',
        'Disallow: /api/admin-actions/',
        f'Disallow: /{admin_url}',
        '',
        f'Sitemap: {base}/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def _build_sitemap_xml():
    """The expensive part of sitemap_xml — registered with cache_kit
    so async refresh can rebuild it out-of-band without blocking a
    user request."""
    from django.conf import settings
    from apps.products.models import Product
    from apps.stores.models import Store

    base = getattr(settings, 'FRONTEND_URL', 'https://micha.app')
    urls = [
        f'<url><loc>{base}/</loc><changefreq>daily</changefreq>'
        f'<priority>1.0</priority></url>'
    ]
    products = Product.objects.filter(
        is_active=True, is_archived=False,
    ).only('slug', 'updated_at').order_by('-updated_at')[:5000]
    for p in products:
        urls.append(
            f'<url>'
            f'<loc>{base}/products/{p.slug}/</loc>'
            f'<lastmod>{p.updated_at.date()}</lastmod>'
            f'<changefreq>weekly</changefreq>'
            f'<priority>0.8</priority>'
            f'</url>'
        )
    stores = Store.objects.filter(is_active=True).only('id', 'updated_at')[:1000]
    for s in stores:
        urls.append(
            f'<url>'
            f'<loc>{base}/stores/{s.id}/</loc>'
            f'<changefreq>weekly</changefreq>'
            f'<priority>0.6</priority>'
            f'</url>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(urls)
        + '\n</urlset>'
    )


def sitemap_xml(request):
    """Crawler endpoint. Expensive build (up to 6000 rows aggregated),
    24h cache. When the cache expires, EVERY crawler that polls in
    the window stampedes the DB simultaneously — Google + Bing alone
    hit this dozens of times per minute. Single-flight + SWR ensures
    one rebuild per cycle even under crawler swarms.
    """
    from apps.core.cache_kit import cached_call
    xml = cached_call(
        'sitemap_xml', _build_sitemap_xml,
        ttl=86400, swr_ttl=3600,
        lock_ttl=60,  # full sitemap build can take ~30s on large catalogs
        waiter_max_retries=240,  # 240 × 50ms = 12s wait — sitemap builds slow
    )
    return HttpResponse(xml, content_type='application/xml')


class ProductSchemaView(APIView):
    """JSON-LD endpoint for product detail pages — Google parses this
    for rich snippets. Hit on every product page view, including by
    crawlers. Viral product → thousands of concurrent requests for
    the same key. Single-flight is essential."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        from apps.core.cache_kit import cached_call, build_key

        # Tag-versioned key — bumping the 'product:<id>' tag (which
        # Product.save() already does) invalidates this entry too.
        cache_key = build_key(
            'schema:product', [f'product:{product_id}'], product_id,
        )

        def _build_schema():
            from apps.products.models import Product
            from django.conf import settings
            from django.shortcuts import get_object_or_404

            product = get_object_or_404(
                Product.objects.select_related('store', 'category')
                .prefetch_related('images'),
                pk=product_id, is_active=True,
            )
            base = getattr(settings, 'FRONTEND_URL', 'https://micha.app')
            schema = {
                '@context': 'https://schema.org/',
                '@type': 'Product',
                'name': product.title,
                'description': (product.description or '')[:500],
                'sku': product.sku or str(product.id),
                'brand': {'@type': 'Brand',
                          'name': product.brand or product.store.name},
                'offers': {
                    '@type': 'Offer',
                    'url': f'{base}/products/{product.slug}/',
                    'priceCurrency': 'AOA',
                    'price': str(product.price),
                    'availability': (
                        'https://schema.org/InStock'
                        if product.quantity > 0
                        else 'https://schema.org/OutOfStock'
                    ),
                    'itemCondition': (
                        'https://schema.org/NewCondition'
                        if product.condition == 'new'
                        else 'https://schema.org/UsedCondition'
                    ),
                    'seller': {'@type': 'Organization',
                               'name': product.store.name},
                },
            }
            images = list(product.images.all())
            if images:
                schema['image'] = [
                    request.build_absolute_uri(img.image.url)
                    for img in images[:5] if img.image
                ]
            if product.category:
                schema['category'] = product.category.name
            return schema

        schema = cached_call(
            cache_key, _build_schema,
            ttl=3600, swr_ttl=1800,
            # 404 on this product is fine to cache briefly — don't
            # let a 404-storm reach the DB.
            negative_ttl=60,
        )
        return Response(schema)
