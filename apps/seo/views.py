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


def sitemap_xml(request):
    cached = cache.get('sitemap_xml')
    if cached:
        return HttpResponse(cached, content_type='application/xml')

    from django.conf import settings
    from apps.products.models import Product
    from apps.stores.models import Store

    base = getattr(settings, 'FRONTEND_URL', 'https://micha.app')
    urls = [
        f'<url><loc>{base}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>'
    ]

    products = Product.objects.filter(
        is_active=True, is_archived=False
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

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(urls)
        + '\n</urlset>'
    )
    cache.set('sitemap_xml', xml, timeout=86400)
    return HttpResponse(xml, content_type='application/xml')


class ProductSchemaView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        cache_key = f'schema:product:{product_id}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        from apps.products.models import Product
        from django.conf import settings
        from django.shortcuts import get_object_or_404

        product = get_object_or_404(
            Product.objects.select_related('store', 'category').prefetch_related('images'),
            pk=product_id, is_active=True
        )
        base = getattr(settings, 'FRONTEND_URL', 'https://micha.app')

        schema = {
            '@context': 'https://schema.org/',
            '@type': 'Product',
            'name': product.title,
            'description': (product.description or '')[:500],
            'sku': product.sku or str(product.id),
            'brand': {'@type': 'Brand', 'name': product.brand or product.store.name},
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
                'seller': {'@type': 'Organization', 'name': product.store.name},
            },
        }

        images = product.images.all()
        if images:
            schema['image'] = [
                request.build_absolute_uri(img.image.url)
                for img in images[:5] if img.image
            ]

        if product.category:
            schema['category'] = product.category.name

        cache.set(cache_key, schema, timeout=3600)
        return Response(schema)
