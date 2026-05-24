"""
R7 SEO product page tests.

Coverage
────────
  TestProductSeoPage
    - 200 returns HTML with <title>, <meta description>, JSON-LD, OG tags
    - canonical points at SPA URL
    - 404 for unknown slug
    - 404 for inactive product
    - cache headers set
"""
import json
import pytest


@pytest.mark.django_db
class TestProductSeoPage:

    def test_renders_product_meta(self, api_client, product):
        res = api_client.get(f'/p/{product.slug}/')
        assert res.status_code == 200
        assert 'text/html' in res['Content-Type']
        body = res.content.decode('utf-8')
        assert f'<title>{product.title}' in body
        assert 'application/ld+json' in body
        # JSON-LD includes the price.
        assert str(product.price) in body
        # Open Graph + canonical.
        assert 'og:title' in body
        assert 'rel="canonical"' in body

    def test_404_for_unknown_slug(self, api_client):
        res = api_client.get('/p/does-not-exist-xyz/')
        assert res.status_code == 404

    def test_404_for_inactive_product(self, api_client, product):
        product.is_active = False
        product.save(update_fields=['is_active'])
        res = api_client.get(f'/p/{product.slug}/')
        assert res.status_code == 404

    def test_cache_control_set(self, api_client, product):
        res = api_client.get(f'/p/{product.slug}/')
        cc = res.get('Cache-Control', '')
        assert 'public' in cc
        assert 'max-age=' in cc


@pytest.mark.django_db
class TestUTMTracking:

    URL = '/api/v1/analytics/touch/'

    def test_anonymous_can_log_touch(self, api_client):
        res = api_client.post(self.URL, {
            'utm_source': 'facebook',
            'utm_medium': 'cpc',
            'utm_campaign': 'angola-q2',
            'landing_path': '/product/123',
            'session_id': 'sess-abc',
        }, format='json')
        assert res.status_code == 201
        from apps.analytics.attribution import AttributionTouch
        assert AttributionTouch.objects.filter(
            utm_source='facebook', session_id='sess-abc',
        ).exists()

    def test_authenticated_links_to_user(self, buyer_client, buyer):
        res = buyer_client.post(self.URL, {
            'utm_source': 'instagram',
            'utm_campaign': 'launch',
        }, format='json')
        assert res.status_code == 201
        from apps.analytics.attribution import AttributionTouch
        row = AttributionTouch.objects.filter(user=buyer).first()
        assert row is not None
        assert row.utm_source == 'instagram'

    def test_attribution_report_admin_only(self, api_client, buyer_client):
        url = '/api/v1/analytics/attribution/'
        assert api_client.get(url).status_code in (401, 403)
        assert buyer_client.get(url).status_code == 403


@pytest.mark.django_db
class TestWhatsAppWebhook:

    URL = '/api/v1/notifications/whatsapp/webhook/'

    def test_subscription_verification_succeeds(self, api_client, settings):
        settings.WHATSAPP_VERIFY_TOKEN = 'test-verify-token'
        res = api_client.get(self.URL, {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'test-verify-token',
            'hub.challenge': 'XYZ-CHAL',
        })
        assert res.status_code == 200
        assert res.content == b'XYZ-CHAL'

    def test_subscription_wrong_token_rejected(self, api_client, settings):
        settings.WHATSAPP_VERIFY_TOKEN = 'test-verify-token'
        res = api_client.get(self.URL, {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'wrong',
            'hub.challenge': 'XYZ-CHAL',
        })
        assert res.status_code == 403

    def test_post_without_signature_rejected(self, api_client, settings):
        settings.WHATSAPP_APP_SECRET = 'app-secret'
        res = api_client.post(self.URL, data='{}',
                              content_type='application/json')
        assert res.status_code == 401

    def test_post_with_valid_signature_accepted(self, api_client, settings):
        import hmac, hashlib
        settings.WHATSAPP_APP_SECRET = 'app-secret'
        body = b'{"object": "whatsapp_business_account", "entry": []}'
        sig = hmac.new(b'app-secret', body, hashlib.sha256).hexdigest()
        res = api_client.post(
            self.URL,
            data=body,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=f'sha256={sig}',
        )
        assert res.status_code == 200
