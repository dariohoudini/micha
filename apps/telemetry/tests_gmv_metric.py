"""
GMV business-metric regression (Monitoring/Logs/Alerts doc CH6).

orders_created counts ORDERS; gmv_kz counts their VALUE. The pair is the
"money flowing" signal that catches a silent failure the order count alone
misses — orders still being placed but at zero/wrong value (a pricing or
total bug) while every tech metric stays green. This locks the metric so it
can't be silently dropped and proves it's exposed on /metrics.
"""
from django.test import SimpleTestCase
from prometheus_client import generate_latest


class GmvMetricTests(SimpleTestCase):
    def test_gmv_metric_declared_and_paired_with_orders(self):
        from apps.telemetry import metrics
        self.assertTrue(hasattr(metrics, 'gmv_kz'))
        self.assertTrue(hasattr(metrics, 'orders_created'))

    def test_gmv_increments_by_value_and_is_exposed(self):
        from apps.telemetry.metrics import gmv_kz
        gmv_kz.labels(payment_method='wallet').inc(1234.0)
        gmv_kz.labels(payment_method='wallet').inc(766.0)
        out = generate_latest().decode()
        self.assertIn('micha_gmv_kz_total', out)
        # cumulative value for the wallet label is at least the 2000 we added
        line = next((ln for ln in out.splitlines()
                     if ln.startswith('micha_gmv_kz_total{payment_method="wallet"}')),
                    None)
        self.assertIsNotNone(line)
        self.assertGreaterEqual(float(line.rsplit(' ', 1)[1]), 2000.0)
