"""
MICHA Input Validators
========================
Reusable validators for all user-supplied input.
Import and use in serializers and views.
"""
import re
import bleach
from django.core.exceptions import ValidationError


# ── Allowed HTML (for product descriptions only) ──────────────────
ALLOWED_TAGS = ['b', 'i', 'u', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li']
ALLOWED_ATTRS = {}


def sanitize_html(value: str) -> str:
    """Strip all dangerous HTML, keep only safe formatting tags."""
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def sanitize_plain_text(value: str) -> str:
    """Strip ALL HTML from plain text fields."""
    return bleach.clean(value, tags=[], attributes={}, strip=True)


# ── Phone number validator ────────────────────────────────────────
ANGOLA_PHONE_RE = re.compile(r'^\+?244[9][1-9]\d{7}$|^[9][1-9]\d{7}$')


def validate_angola_phone(value: str):
    """Validate Angolan phone number format."""
    digits = re.sub(r'\D', '', value)
    if not (9 <= len(digits) <= 12):
        raise ValidationError('Número de telefone inválido')
    return value


# ── NIF validator ─────────────────────────────────────────────────
NIF_RE = re.compile(r'^\d{10}$')


def validate_nif(value: str):
    """Validate Angolan NIF format (10 digits)."""
    if not NIF_RE.match(str(value).strip()):
        raise ValidationError('NIF inválido — deve ter 10 dígitos')
    return value


# ── Price validator ───────────────────────────────────────────────
def validate_price(value, min_price=100, max_price=50_000_000):
    """Validate product price in AOA."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise ValidationError('Preço inválido')
    if price < min_price:
        raise ValidationError(f'Preço mínimo é {min_price} AOA')
    if price > max_price:
        raise ValidationError(f'Preço máximo é {max_price:,} AOA')
    return value


# ── String length validators ──────────────────────────────────────
def validate_max_length(value: str, max_length: int, field_name: str = 'Campo'):
    if len(str(value)) > max_length:
        raise ValidationError(f'{field_name} não pode ter mais de {max_length} caracteres')
    return value


# ── URL validator ─────────────────────────────────────────────────
SAFE_URL_RE = re.compile(r'^https?://', re.IGNORECASE)


def validate_safe_url(value: str):
    """Ensure URLs are http/https only — prevent javascript: and data: URIs."""
    if value and not SAFE_URL_RE.match(value):
        raise ValidationError('URL inválido — deve começar com http:// ou https://')
    return value


# ── Search query sanitizer ────────────────────────────────────────
def sanitize_search_query(query: str, max_length: int = 200) -> str:
    """Clean and limit search queries."""
    # Remove HTML
    query = bleach.clean(query, tags=[], strip=True)
    # Remove SQL-like patterns
    query = re.sub(r'[;\-\-\'\"\\]', '', query)
    # Limit length
    return query[:max_length].strip()


# ── Filename sanitizer ────────────────────────────────────────────
SAFE_FILENAME_RE = re.compile(r'[^\w\s\-_\.]')


def sanitize_filename(filename: str) -> str:
    """Remove dangerous characters from filenames."""
    import os
    name, ext = os.path.splitext(filename)
    name = SAFE_FILENAME_RE.sub('', name)[:50]
    ext = ext.lower()[:10]
    return f'{name}{ext}' if name else 'file'
