"""
Canonical health-probe path regression (Hosting & Deployment doc CH8/CH11).

The Dockerfile HEALTHCHECK targets /health/live and the Nginx /health/*
location + load-balancer readiness probe target /health/ready. These must
resolve to the liveness / readiness handlers respectively, or the container
healthcheck silently fails and unready instances keep receiving traffic.
"""
from django.test import SimpleTestCase
from django.urls import resolve


class CanonicalHealthPathTests(SimpleTestCase):
    def test_health_live_is_liveness_handler(self):
        self.assertEqual(resolve('/health/live').func.__name__, 'healthz')

    def test_health_ready_is_readiness_handler(self):
        self.assertEqual(resolve('/health/ready').func.__name__, 'readyz')

    def test_legacy_probe_paths_still_resolve(self):
        # Existing callers must keep working.
        self.assertEqual(resolve('/healthz').func.__name__, 'healthz')
        self.assertEqual(resolve('/readyz').func.__name__, 'readyz')

    def test_version_endpoint_resolves(self):
        # CI/CD & VC doc CH13/CH20 — "what version is live?" answerable.
        self.assertEqual(resolve('/version').func.__name__, 'build_info')


class BuildInfoTests(SimpleTestCase):
    def setUp(self):
        from django.test import Client
        self.client = Client()

    def test_dev_returns_safe_placeholders(self):
        import json
        r = self.client.get('/version', HTTP_HOST='localhost')
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        self.assertEqual(body['service'], 'micha-backend')
        # never leaks; placeholders when the pipeline hasn't stamped env.
        self.assertIn('version', body)
        self.assertIn('commit', body)
        self.assertIn('build_time', body)

    def test_pipeline_stamped_env_is_surfaced(self):
        import json
        with self.settings():
            import os
            old = {k: os.environ.get(k) for k in ('APP_VERSION', 'GIT_SHA')}
            os.environ['APP_VERSION'] = '9.9.9'
            os.environ['GIT_SHA'] = 'deadbeef'
            try:
                body = json.loads(
                    self.client.get('/version', HTTP_HOST='localhost').content)
                self.assertEqual(body['version'], '9.9.9')
                self.assertEqual(body['commit'], 'deadbeef')
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
