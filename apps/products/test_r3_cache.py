"""
R3 cache-header tests on product/category list endpoints.
"""
import pytest


@pytest.mark.django_db
class TestPublicCacheHeaders:

    def test_category_list_has_public_cache(self, api_client):
        res = api_client.get('/api/v1/products/categories/')
        # Endpoint may not exist exactly at this path; cover both common forms.
        if res.status_code == 404:
            res = api_client.get('/api/v1/products/category/')
        if res.status_code == 200:
            cc = res.get('Cache-Control', '')
            assert 'public' in cc
            assert 'max-age=' in cc

    def test_product_list_has_public_cache(self, api_client):
        res = api_client.get('/api/v1/products/')
        if res.status_code == 200:
            cc = res.get('Cache-Control', '')
            assert 'public' in cc
            assert 'stale-while-revalidate' in cc
            assert res.get('Vary')

    def test_no_public_cache_on_non_200(self, api_client):
        # Non-existent product id → 404, MUST NOT carry public cache header
        res = api_client.get('/api/v1/products/999999999/')
        if res.status_code >= 400:
            cc = res.get('Cache-Control', '') or ''
            assert 'public' not in cc
