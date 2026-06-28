"""
apps/core/api_errors.py — raise canonical domain errors from anywhere.

Lets service / view code raise a single exception carrying a canonical
CH4 code; the DRF exception handler resolves status, message, snake alias,
and documentation_url from the catalogue and emits the superset envelope.

    from apps.core.api_errors import ApiError

    if available < qty:
        raise ApiError('INSUFFICIENT_STOCK')          # 409 + canonical body
    raise ApiError('COD_NOT_AVAILABLE',
                   detail='COD não disponível na província do Cunene.')

This keeps domain code from hand-building error dicts and guarantees the
machine code matches the catalogue exactly.
"""
from __future__ import annotations

from rest_framework.exceptions import APIException

from apps.core.error_catalogue import (
    alias_for, canonical_code, message_for, status_for,
)


class ApiError(APIException):
    """A canonical, catalogue-backed API error.

    ``code`` should be a key in apps.core.error_catalogue.CATALOGUE.
    Unknown codes still work (uppercased, status defaults from the catalogue
    fallback) so this never blocks a caller — but prefer catalogue codes.
    """

    def __init__(self, code: str, *, detail: str | None = None,
                 field_errors: dict | None = None, status: int | None = None):
        self.canonical = canonical_code(code, status or 400)
        self.status_code = status or status_for(self.canonical) or 400
        self.snake_code = alias_for(self.canonical) or self.canonical.lower()
        self.field_errors = field_errors
        # The DRF .detail becomes the human message; the handler keeps it.
        self.message = detail or message_for(self.canonical) or 'Error.'
        super().__init__(detail=self.message)

    def as_body(self) -> dict:
        body = {'error': self.snake_code, 'detail': self.message}
        if self.field_errors:
            body['field_errors'] = self.field_errors
        return body
