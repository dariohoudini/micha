"""
apps/seo/prerender.py
──────────────────────

Server-rendered product page shell for SEO (R7).

Why this exists
───────────────
The SPA is client-rendered — Googlebot sees an empty <body> and
no <title>/<meta>/<link rel="canonical">/JSON-LD. Product pages
are therefore invisible to search and we lose all the free-traffic
upside of organic search referrals.

This view emits a minimal HTML page with:
  • <title> + <meta description> from Product
  • <link rel="canonical"> to the SPA URL
  • Open Graph + Twitter Card meta (rich previews on social)
  • Inline JSON-LD (schema.org/Product) — same payload as
    apps.seo.views.ProductSchemaView but inlined so crawlers don't
    need a second fetch
  • Meta refresh + JS redirect to the SPA route so human users
    arrive at the interactive page

Search engines parse the SEO surface; humans get redirected to the
SPA. Best of both worlds without paying the Next.js migration tax.

Route
─────
Mounted at /p/<slug>/  in config/urls.py.
Crawlers + share-link rendering hit this; the SPA's product detail
page at /product/<id> remains the canonical interactive URL.
"""
from __future__ import annotations

import html
import json
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.cache import patch_cache_control


def _esc(value) -> str:
    """HTML-escape + truncate for safe injection into the page head."""
    return html.escape((str(value or ''))[:500])


def _absolute_url(request, path: str) -> str:
    """Build a canonical absolute URL from a relative path."""
    base = getattr(settings, 'FRONTEND_URL', 'https://micha.ao')
    return f"{base.rstrip('/')}{path}"


def render_product_seo(request, slug: str):
    """``GET /p/<slug>/`` — SEO-rendered product page shell."""
    try:
        from apps.products.models import Product
    except Exception:
        return HttpResponseNotFound()

    product = (
        Product.objects
        .select_related('store', 'category')
        .prefetch_related('images')
        .filter(slug=slug, is_active=True)
        .first()
    )
    if product is None:
        return HttpResponseNotFound()

    spa_url = f"/product/{product.pk}"
    canonical = _absolute_url(request, spa_url)
    title = f"{product.title} — MICHA"
    description = (product.description or product.title or '')[:160]

    primary_image = ''
    for img in product.images.all():
        if img and getattr(img, 'image', None):
            primary_image = request.build_absolute_uri(img.image.url)
            break

    json_ld = {
        '@context': 'https://schema.org/',
        '@type': 'Product',
        'name': product.title,
        'description': (product.description or '')[:500],
        'sku': product.sku or str(product.pk),
        'brand': {
            '@type': 'Brand',
            'name': product.brand or product.store.name,
        },
        'offers': {
            '@type': 'Offer',
            'url': canonical,
            'priceCurrency': 'AOA',
            'price': str(product.price),
            'availability': (
                'https://schema.org/InStock'
                if product.quantity > 0
                else 'https://schema.org/OutOfStock'
            ),
            'itemCondition': (
                'https://schema.org/NewCondition'
                if getattr(product, 'condition', 'new') == 'new'
                else 'https://schema.org/UsedCondition'
            ),
            'seller': {'@type': 'Organization',
                       'name': product.store.name},
        },
    }
    if primary_image:
        json_ld['image'] = primary_image

    body = (
        '<!DOCTYPE html>\n'
        '<html lang="pt-AO">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{_esc(title)}</title>\n'
        f'<meta name="description" content="{_esc(description)}">\n'
        f'<link rel="canonical" href="{_esc(canonical)}">\n'

        # Open Graph
        '<meta property="og:type" content="product">\n'
        f'<meta property="og:title" content="{_esc(title)}">\n'
        f'<meta property="og:description" content="{_esc(description)}">\n'
        f'<meta property="og:url" content="{_esc(canonical)}">\n'
        + (f'<meta property="og:image" content="{_esc(primary_image)}">\n'
           if primary_image else '')
        + '<meta property="og:site_name" content="MICHA">\n'
        + f'<meta property="product:price:amount" content="{_esc(product.price)}">\n'
        + '<meta property="product:price:currency" content="AOA">\n'

        # Twitter Card
        + '<meta name="twitter:card" content="summary_large_image">\n'
        + f'<meta name="twitter:title" content="{_esc(title)}">\n'
        + f'<meta name="twitter:description" content="{_esc(description)}">\n'
        + (f'<meta name="twitter:image" content="{_esc(primary_image)}">\n'
           if primary_image else '')

        + '<script type="application/ld+json">'
        + json.dumps(json_ld, ensure_ascii=False, separators=(',', ':'))
        + '</script>\n'

        # JS redirect for human visitors. Meta-refresh fallback for
        # browsers with JS disabled or for crawlers that follow redirects.
        + f'<script>window.location.replace({json.dumps(spa_url)});</script>\n'
        + f'<meta http-equiv="refresh" content="0;url={_esc(spa_url)}">\n'
        '</head>\n'
        '<body>\n'
        f'<h1>{_esc(product.title)}</h1>\n'
        f'<p>{_esc(description)}</p>\n'
        f'<p>Price: {_esc(product.price)} AOA</p>\n'
        f'<p><a href="{_esc(spa_url)}">Open in MICHA app</a></p>\n'
        '</body>\n'
        '</html>\n'
    )

    response = HttpResponse(body, content_type='text/html; charset=utf-8')
    # CDN-cacheable. Stale window long enough that price changes
    # propagate within minutes when SPA invalidates the product tag.
    patch_cache_control(response, public=True, max_age=300)
    return response
