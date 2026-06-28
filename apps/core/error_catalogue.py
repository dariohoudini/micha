"""
apps/core/error_catalogue.py — canonical error code catalogue.

Single source of truth for the standard error catalogue specified in
API & Backend doc Part 1, CH4.3. Every error the API emits resolves to a
STABLE, machine-parseable UPPERCASE code here, with a defined HTTP status,
a localised default message (pt-AO), and a documentation slug.

Why this exists
---------------
The codebase already shipped a working error envelope keyed by a
snake_case ``error`` field (e.g. ``"validation_error"``) that the frontend
reads. The doc asks for a stable machine code catalogue with http_status
and a documentation_url. Rather than break the live frontend, we keep the
snake_case ``error`` AND additively expose the canonical UPPERCASE ``code``
(plus ``http_status`` / ``documentation_url``) on every error body — a
superset. This module is the bridge between the two:

    snake_case alias  <->  CANONICAL_CODE  ->  (status, message, doc_slug)

New domain code should raise ``apps.core.exceptions.ApiError('SOME_CODE')``
with a code from this catalogue; the exception handler resolves the rest.
"""
from __future__ import annotations

DOC_BASE = 'https://docs.micha.ao/errors/'

# code -> (http_status, default pt-AO message, snake_case legacy alias)
# The legacy alias is what the existing ``error`` field and frontend use;
# the dict KEY is the canonical CH4 code surfaced as ``code``.
CATALOGUE: dict[str, tuple[int, str, str]] = {
    # ── Authentication / Authorisation ──────────────────────────────
    'AUTH_REQUIRED':            (401, 'Autenticação necessária.', 'authentication_required'),
    'AUTH_TOKEN_INVALID':       (401, 'Token inválido.', 'token_invalid'),
    'AUTH_TOKEN_EXPIRED':       (401, 'Sessão expirada. Inicie sessão novamente.', 'token_expired'),
    'AUTH_FORBIDDEN':           (403, 'Não tem permissão para esta acção.', 'permission_denied'),
    'AUTH_ACCOUNT_SUSPENDED':   (403, 'Conta suspensa.', 'account_suspended'),
    'AUTH_KYC_REQUIRED':        (403, 'Esta acção requer verificação de identidade (KYC).', 'kyc_required'),
    'AUTH_INVALID_CREDENTIALS': (401, 'Credenciais inválidas.', 'invalid_credentials'),

    # ── Validation / Input ──────────────────────────────────────────
    'VALIDATION_ERROR':         (400, 'A validação falhou.', 'validation_error'),
    'MISSING_REQUIRED_FIELD':   (400, 'Campo obrigatório em falta.', 'missing_required_field'),
    'INVALID_FORMAT':           (422, 'Formato inválido.', 'invalid_format'),
    'INVALID_ENUM_VALUE':       (422, 'Valor não permitido.', 'invalid_enum_value'),

    # ── Resource / State ────────────────────────────────────────────
    'RESOURCE_NOT_FOUND':       (404, 'O recurso solicitado não foi encontrado.', 'not_found'),
    'RESOURCE_CONFLICT':        (409, 'Conflito de estado.', 'conflict'),
    'RESOURCE_GONE':            (410, 'O recurso foi removido permanentemente.', 'gone'),
    'STATE_TRANSITION_INVALID': (409, 'Transição de estado inválida.', 'state_transition_invalid'),

    # ── Rate / Idempotency ──────────────────────────────────────────
    'RATE_LIMIT_EXCEEDED':      (429, 'Demasiados pedidos. Abrande e tente novamente.', 'rate_limited'),
    'IDEMPOTENCY_KEY_REQUIRED': (400, 'Este pedido requer um cabeçalho Idempotency-Key.', 'idempotency_key_required'),
    'IDEMPOTENCY_KEY_CONFLICT': (409, 'Idempotency-Key reutilizada com um corpo de pedido diferente.', 'idempotency_key_conflict'),
    'IDEMPOTENCY_IN_PROGRESS':  (409, 'Um pedido com esta Idempotency-Key está a ser processado.', 'idempotency_in_progress'),

    # ── Domain-specific (Part 1 + Part 2) ───────────────────────────
    'INSUFFICIENT_STOCK':       (409, 'Stock insuficiente.', 'insufficient_stock'),
    'PAYMENT_DECLINED':         (402, 'Pagamento recusado.', 'payment_declined'),
    'COD_NOT_AVAILABLE':        (422, 'Pagamento na entrega não disponível para este destino.', 'cod_not_available'),
    'CART_ITEM_UNAVAILABLE':    (409, 'Um artigo do carrinho deixou de estar disponível.', 'cart_item_unavailable'),
    'ORDER_NOT_CANCELLABLE':    (409, 'A encomenda já não pode ser cancelada.', 'order_not_cancellable'),
    'COUPON_INVALID':           (422, 'Cupão inválido, expirado ou já utilizado.', 'coupon_invalid'),
    # Part 2 CH29 — coupon engine error codes (distinct reasons so the
    # client can show the precise cause to the buyer).
    'COUPON_EXPIRED':           (422, 'Cupão expirado.', 'coupon_expired'),
    'COUPON_EXHAUSTED':         (409, 'Cupão esgotado (limite total atingido).', 'coupon_exhausted'),
    'COUPON_USED':              (409, 'Já utilizou este cupão.', 'coupon_used'),
    'COUPON_MIN_NOT_MET':       (422, 'O valor mínimo da encomenda não foi atingido.', 'coupon_min_not_met'),
    'COUPON_NOT_APPLICABLE':    (422, 'Cupão não aplicável a estes artigos.', 'coupon_not_applicable'),
    # Part 2 CH22 — wallet.
    'WALLET_INSUFFICIENT':      (402, 'Saldo da carteira insuficiente.', 'wallet_insufficient'),
    'WALLET_FROZEN':            (403, 'A carteira está congelada.', 'wallet_frozen'),
    # Part 2 CH33 — webhook security.
    'WEBHOOK_SIGNATURE_INVALID': (401, 'Assinatura de webhook inválida.', 'webhook_signature_invalid'),

    # ── System ──────────────────────────────────────────────────────
    'INTERNAL_ERROR':           (500, 'Ocorreu um erro interno. A nossa equipa foi notificada.', 'server_error'),
    'SERVICE_UNAVAILABLE':      (503, 'Serviço temporariamente indisponível.', 'service_unavailable'),
    'DEPENDENCY_TIMEOUT':       (504, 'Um serviço externo demorou demasiado a responder.', 'dependency_timeout'),
}

# Reverse index: snake_case alias -> CANONICAL_CODE (first wins on dupes).
_ALIAS_TO_CODE: dict[str, str] = {}
for _code, (_status, _msg, _alias) in CATALOGUE.items():
    _ALIAS_TO_CODE.setdefault(_alias, _code)

# Status -> canonical code fallback when nothing more specific is known.
# Mirrors apps/core/responses._STATUS_TO_CODE but in canonical form.
_STATUS_TO_CANONICAL = {
    400: 'VALIDATION_ERROR',
    401: 'AUTH_REQUIRED',
    403: 'AUTH_FORBIDDEN',
    404: 'RESOURCE_NOT_FOUND',
    409: 'RESOURCE_CONFLICT',
    410: 'RESOURCE_GONE',
    422: 'VALIDATION_ERROR',
    429: 'RATE_LIMIT_EXCEEDED',
    402: 'PAYMENT_DECLINED',
    503: 'SERVICE_UNAVAILABLE',
    504: 'DEPENDENCY_TIMEOUT',
}


def canonical_code(snake_or_code: str | None, status_code: int) -> str:
    """Resolve a snake_case alias (or already-canonical code) to the
    canonical UPPERCASE code. Falls back to the status-derived code, then
    to a sensible default."""
    if snake_or_code:
        s = str(snake_or_code)
        if s in CATALOGUE:                       # already canonical
            return s
        if s in _ALIAS_TO_CODE:                  # snake alias
            return _ALIAS_TO_CODE[s]
        # Unknown but code-like — uppercase it so it's still machine-stable.
        if ' ' not in s and len(s) <= 60:
            return s.upper()
    if status_code >= 500:
        return 'INTERNAL_ERROR'
    return _STATUS_TO_CANONICAL.get(status_code, 'VALIDATION_ERROR'
                                    if status_code < 500 else 'INTERNAL_ERROR')


def status_for(code: str) -> int | None:
    entry = CATALOGUE.get(code)
    return entry[0] if entry else None


def message_for(code: str) -> str | None:
    entry = CATALOGUE.get(code)
    return entry[1] if entry else None


def alias_for(code: str) -> str | None:
    """Canonical code -> snake_case alias (for the legacy ``error`` field)."""
    entry = CATALOGUE.get(code)
    return entry[2] if entry else None


def documentation_url(code: str) -> str:
    return DOC_BASE + code
