"""
R5-C deep-link verification file tests.

Coverage
────────
  TestAppleAppSiteAssociation
    - returns 200 + JSON content-type at /.well-known/apple-app-site-association
    - empty-but-valid shape when IOS_TEAM_ID unset
    - configured shape when team + bundle set
    - public cache headers present (Apple caches aggressively)

  TestAssetlinksJson
    - returns 200 + JSON at /.well-known/assetlinks.json
    - empty array when package + fingerprints unset
    - configured shape when both set
    - accepts comma-separated string for ANDROID_SHA256_FINGERPRINTS
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.django_db
class TestAppleAppSiteAssociation:

    URL = '/.well-known/apple-app-site-association'

    def test_responds_200_with_json_content_type(self, api_client):
        res = api_client.get(self.URL)
        assert res.status_code == 200
        ct = res['Content-Type']
        assert 'application/json' in ct

    def test_empty_shape_when_team_id_missing(self, api_client, settings):
        settings.IOS_TEAM_ID = ''
        res = api_client.get(self.URL)
        assert res.status_code == 200
        body = json.loads(res.content)
        # Valid AASA structure even with no apps configured.
        assert body == {'applinks': {'details': []}}

    def test_configured_shape_when_team_and_bundle_set(self, api_client, settings):
        settings.IOS_TEAM_ID = 'ABCDE12345'
        settings.IOS_BUNDLE_ID = 'ao.micha.express'
        res = api_client.get(self.URL)
        body = json.loads(res.content)
        details = body['applinks']['details']
        assert len(details) == 1
        assert details[0]['appIDs'] == ['ABCDE12345.ao.micha.express']
        # Confirm critical link patterns are claimed.
        paths = [c['/'] for c in details[0]['components']]
        assert '/product/*' in paths
        assert '/order/*' in paths
        assert '/auth/callback/*' in paths

    def test_cache_control_header_set(self, api_client, settings):
        settings.IOS_TEAM_ID = 'ABCDE12345'
        res = api_client.get(self.URL)
        cc = res.get('Cache-Control', '')
        # Should be cacheable for at least an hour.
        assert 'public' in cc or 'max-age' in cc


@pytest.mark.django_db
class TestAssetlinksJson:

    URL = '/.well-known/assetlinks.json'

    def test_responds_200_with_json(self, api_client, settings):
        settings.ANDROID_PACKAGE_NAME = ''
        settings.ANDROID_SHA256_FINGERPRINTS = []
        res = api_client.get(self.URL)
        assert res.status_code == 200

    def test_empty_array_when_unconfigured(self, api_client, settings):
        settings.ANDROID_PACKAGE_NAME = ''
        settings.ANDROID_SHA256_FINGERPRINTS = []
        res = api_client.get(self.URL)
        body = json.loads(res.content)
        assert body == []

    def test_configured_shape(self, api_client, settings):
        settings.ANDROID_PACKAGE_NAME = 'ao.micha.express'
        settings.ANDROID_SHA256_FINGERPRINTS = [
            'AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99',
        ]
        res = api_client.get(self.URL)
        body = json.loads(res.content)
        assert isinstance(body, list)
        assert len(body) == 1
        entry = body[0]
        assert entry['target']['package_name'] == 'ao.micha.express'
        assert 'delegate_permission/common.handle_all_urls' in entry['relation']
        assert len(entry['target']['sha256_cert_fingerprints']) == 1

    def test_accepts_comma_separated_fingerprints(self, api_client, settings):
        """ops convenience: a comma-separated env var should parse as
        a list of fingerprints."""
        settings.ANDROID_PACKAGE_NAME = 'ao.micha.express'
        settings.ANDROID_SHA256_FINGERPRINTS = 'AA:BB,CC:DD,EE:FF'
        res = api_client.get(self.URL)
        body = json.loads(res.content)
        fps = body[0]['target']['sha256_cert_fingerprints']
        assert fps == ['AA:BB', 'CC:DD', 'EE:FF']
