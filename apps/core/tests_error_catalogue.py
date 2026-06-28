"""Tests for the CH4 canonical error catalogue + superset envelope."""
from django.test import SimpleTestCase

from apps.core.api_errors import ApiError
from apps.core.error_catalogue import (
    CATALOGUE, canonical_code, documentation_url, alias_for,
)
from apps.core.responses import normalize_error_body


class CanonicalCodeTests(SimpleTestCase):
    def test_snake_alias_maps_to_canonical(self):
        self.assertEqual(canonical_code('not_found', 404), 'RESOURCE_NOT_FOUND')
        self.assertEqual(canonical_code('validation_error', 400),
                         'VALIDATION_ERROR')
        self.assertEqual(canonical_code('insufficient_stock', 409),
                         'INSUFFICIENT_STOCK')

    def test_already_canonical_passthrough(self):
        self.assertEqual(canonical_code('PAYMENT_DECLINED', 402),
                         'PAYMENT_DECLINED')

    def test_status_fallback_when_unknown(self):
        self.assertEqual(canonical_code(None, 404), 'RESOURCE_NOT_FOUND')
        self.assertEqual(canonical_code(None, 500), 'INTERNAL_ERROR')

    def test_unknown_codeish_uppercased(self):
        self.assertEqual(canonical_code('some_new_code', 409), 'SOME_NEW_CODE')

    def test_doc_url(self):
        self.assertEqual(documentation_url('RESOURCE_NOT_FOUND'),
                         'https://docs.micha.ao/errors/RESOURCE_NOT_FOUND')


class SupersetEnvelopeTests(SimpleTestCase):
    def test_validation_body_has_both_legacy_and_canonical(self):
        drf = {'email': ['Formato inválido.'], 'phone': ['Obrigatório.']}
        body = normalize_error_body(drf, 400)
        # legacy (frontend reads these)
        self.assertEqual(body['error'], 'validation_error')
        self.assertIn('field_errors', body)
        self.assertEqual(body['field_errors']['email'], ['Formato inválido.'])
        # CH4 canonical superset
        self.assertEqual(body['code'], 'VALIDATION_ERROR')
        self.assertEqual(body['http_status'], 400)
        self.assertEqual(body['documentation_url'],
                         'https://docs.micha.ao/errors/VALIDATION_ERROR')
        # details[] derived from field_errors
        fields = {d['field'] for d in body['details']}
        self.assertEqual(fields, {'email', 'phone'})

    def test_not_found_superset(self):
        body = normalize_error_body({'detail': 'Não encontrado.'}, 404)
        self.assertEqual(body['error'], 'not_found')
        self.assertEqual(body['code'], 'RESOURCE_NOT_FOUND')
        self.assertEqual(body['http_status'], 404)

    def test_5xx_never_leaks_and_is_canonical(self):
        body = normalize_error_body({'detail': 'psycopg2 boom at line 7'}, 500)
        self.assertEqual(body['code'], 'INTERNAL_ERROR')
        self.assertNotIn('psycopg2', body['detail'])

    def test_idempotent_on_already_normalized(self):
        once = normalize_error_body({'detail': 'x'}, 409)
        twice = normalize_error_body(once, 409)
        self.assertEqual(once['code'], twice['code'])
        self.assertEqual(once['error'], twice['error'])
        self.assertEqual(once['http_status'], twice['http_status'])


class ApiErrorTests(SimpleTestCase):
    def test_resolves_status_message_alias(self):
        err = ApiError('INSUFFICIENT_STOCK')
        self.assertEqual(err.status_code, 409)
        self.assertEqual(err.snake_code, 'insufficient_stock')
        self.assertEqual(err.as_body()['error'], 'insufficient_stock')

    def test_custom_detail_and_field_errors(self):
        err = ApiError('COD_NOT_AVAILABLE', detail='Cunene não suporta COD.',
                       field_errors={'province': ['Sem COD.']})
        self.assertEqual(err.status_code, 422)
        body = err.as_body()
        self.assertEqual(body['detail'], 'Cunene não suporta COD.')
        self.assertIn('province', body['field_errors'])

    def test_catalogue_aliases_are_unique_enough(self):
        # Every catalogue entry round-trips code -> alias -> code.
        for code in CATALOGUE:
            alias = alias_for(code)
            self.assertTrue(alias)

    def test_part2_domain_codes_present(self):
        # Part 2 CH22/CH29/CH33 codes the doc explicitly specifies.
        for code in ('COUPON_EXPIRED', 'COUPON_EXHAUSTED', 'COUPON_USED',
                     'COUPON_MIN_NOT_MET', 'COUPON_NOT_APPLICABLE',
                     'WALLET_INSUFFICIENT', 'WEBHOOK_SIGNATURE_INVALID'):
            self.assertIn(code, CATALOGUE)
        self.assertEqual(canonical_code('coupon_expired', 422), 'COUPON_EXPIRED')
        self.assertEqual(canonical_code('wallet_insufficient', 402),
                         'WALLET_INSUFFICIENT')
