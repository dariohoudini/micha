"""
Off-Platform Contact Scanner
Detects phone numbers and email addresses in user-generated content.
Prevents users from bypassing MICHA's commission system (T&C §4.2).
"""
import re

PHONE_PATTERN = re.compile(
    r'(\+?\d[\d\s\-\.]{7,}\d|\b9\d{8}\b|\+244[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{3})'
)
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
)
SOCIAL_PATTERN = re.compile(
    r'(whatsapp|telegram|instagram|facebook|snapchat|tiktok|t\.me/|wa\.me/)',
    re.IGNORECASE
)

def scan_for_offplatform_contact(text):
    """
    Returns list of violations found in text.
    Empty list means clean.
    """
    violations = []
    if PHONE_PATTERN.search(text):
        violations.append('phone number')
    if EMAIL_PATTERN.search(text):
        violations.append('email address')
    if SOCIAL_PATTERN.search(text):
        violations.append('social media contact')
    return violations

def validate_no_offplatform_contact(text):
    """Django validator — raises ValidationError if contact info found."""
    from django.core.exceptions import ValidationError
    violations = scan_for_offplatform_contact(text)
    if violations:
        raise ValidationError(
            f'Your message contains {", ".join(violations)}. '
            'Sharing contact information to conduct transactions outside MICHA '
            'is not permitted under our Terms of Service (§4.2).'
        )
