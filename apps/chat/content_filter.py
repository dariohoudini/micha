"""
apps/chat/content_filter.py

Off-platform transaction detection in chat.
BRD requirement: prevent sellers/buyers from moving transactions outside MICHA.

Detects and blocks:
- Phone numbers (WhatsApp fraud prevention)
- External payment requests (Multicaixa direct, bank accounts)
- External links (taking buyers off platform)
- Email addresses in chat
"""
import re
import logging

logger = logging.getLogger(__name__)


# ── Detection patterns ────────────────────────────────────────────────────────

PHONE_PATTERNS = [
    r'\+244\s?\d{3}\s?\d{3}\s?\d{3}',     # Angola +244 9XX XXX XXX
    r'9[2-9]\d\s?\d{3}\s?\d{3}',           # Local Angola 9XX XXX XXX
    r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # Generic international
    r'wh?at?s?app',                          # WhatsApp mentions
    r'zap\s*:?\s*\d',                        # "zap" (WhatsApp nickname in Angola)
    r'ligar[- ]me',                          # "call me" in Portuguese
    r'liga[- ]para',
]

PAYMENT_PATTERNS = [
    r'multicaixa\s*(express)?\s*:\s*\d',   # Multicaixa number directly
    r'iban\s*:?\s*[A-Z]{2}\d{2}',          # Bank IBAN
    r'n[uú]mero\s*de\s*conta',              # Account number request
    r'pague?\s*(fora|directo|direct)',      # Pay outside
    r'transfer[eê]ncia\s*banc[aá]ria',     # Bank transfer
    r'pix',                                 # Brazilian payment (regional)
    r'paypal',
    r'western\s*union',
    r'money\s*gram',
]

EXTERNAL_LINK_PATTERNS = [
    r'https?://(?!micha\.ao)',              # Any URL except micha.ao
    r'bit\.ly', r'tinyurl', r'shorturl',   # URL shorteners (suspicious)
]

EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

# Messages that give context — not blocked but flagged for review
SUSPICIOUS_PATTERNS = [
    r'fora\s*da\s*(plataforma|app)',        # "outside the platform"
    r'contacta[- ]me',                      # "contact me"
    r'envia[- ]me\s*(o\s*)?n[uú]mero',     # "send me the number"
]


class ChatContentFilter:
    """
    Filters chat messages for off-platform transaction attempts.
    Called before every message is saved/delivered.
    """

    @classmethod
    def check_message(cls, message: str, sender_id: str = None) -> dict:
        """
        Checks a message for policy violations.

        Returns:
        {
            'allowed': bool,
            'violations': [{'type': str, 'severity': 'block'|'warn', 'message': str}],
            'cleaned_message': str,  # message with violations redacted
        }
        """
        if not message:
            return {'allowed': True, 'violations': [], 'cleaned_message': message}

        violations = []
        cleaned = message

        # Check phone numbers — BLOCK
        for pattern in PHONE_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                violations.append({
                    'type': 'phone_number',
                    'severity': 'block',
                    'message': 'Não é permitido partilhar números de telefone no chat. Use os contactos da MICHA Express.',
                })
                cleaned = re.sub(pattern, '[número removido]', cleaned, flags=re.IGNORECASE)
                break

        # Check external payment requests — BLOCK
        for pattern in PAYMENT_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                violations.append({
                    'type': 'external_payment',
                    'severity': 'block',
                    'message': 'Não é permitido solicitar pagamentos fora da plataforma. Use o checkout seguro da MICHA Express.',
                })
                break

        # Check external links — BLOCK
        for pattern in EXTERNAL_LINK_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                violations.append({
                    'type': 'external_link',
                    'severity': 'block',
                    'message': 'Não é permitido partilhar links externos no chat.',
                })
                cleaned = re.sub(pattern, '[link removido]', cleaned, flags=re.IGNORECASE)
                break

        # Check email — WARN (don't block, just flag)
        if re.search(EMAIL_PATTERN, message):
            violations.append({
                'type': 'email_address',
                'severity': 'warn',
                'message': 'Lembrete: mantenha toda a comunicação dentro da plataforma.',
            })

        # Check suspicious patterns — WARN
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                violations.append({
                    'type': 'suspicious_language',
                    'severity': 'warn',
                    'message': 'Esta mensagem foi sinalizada para revisão.',
                })
                # Log for admin review
                logger.warning(f"Suspicious chat message from {sender_id}: {message[:100]}")
                break

        # Block if any hard violations
        block_violations = [v for v in violations if v['severity'] == 'block']
        allowed = len(block_violations) == 0

        return {
            'allowed': allowed,
            'violations': violations,
            'cleaned_message': cleaned if allowed else message,
            'block_reason': block_violations[0]['message'] if block_violations else None,
        }

    @classmethod
    def get_warning_message(cls, violation_type: str) -> str:
        """Returns user-facing warning message in Portuguese."""
        messages = {
            'phone_number': '🚫 Número de telefone detectado. Por segurança, a partilha de contactos não é permitida no chat. Efectue a sua compra pelo checkout seguro da MICHA Express.',
            'external_payment': '🚫 Pedido de pagamento externo detectado. Todos os pagamentos devem ser feitos pela MICHA Express para a sua protecção.',
            'external_link': '🚫 Link externo detectado e removido.',
            'email_address': '⚠️ Lembrete: mantenha toda a comunicação dentro da MICHA Express para a sua segurança.',
            'suspicious_language': '⚠️ Esta mensagem foi sinalizada. Certifique-se de que todas as transacções são feitas dentro da plataforma.',
        }
        return messages.get(violation_type, '⚠️ Mensagem sinalizada.')
