"""
apps/moderation/brand_registry.py
──────────────────────────────────

Brand protection registry (R4).

Why this exists
───────────────
Counterfeits are ~30% of African e-commerce reports. Without a brand
registry, every listing using "Nike" / "Apple" / "Samsung" rolls
through the standard moderation queue indistinguishable from real
sellers. Six months in, the platform becomes a counterfeit haven
and real brands either complain (lawsuits) or block the marketplace
(Apple has done this).

Model: ProtectedBrand
─────────────────────
  name          'Nike'                            (case-insensitive search)
  variants      ['nike', 'just do it', 'swoosh']  any-match
  owner_email   contact at the trademark holder
  policy        'review' | 'block' | 'manual'
  added_by      admin who registered the brand
  added_at, updated_at

When a Product / Listing creation event includes a brand mention from
the registry, the moderation service auto-routes the item to a
special high-priority queue tagged 'brand_match'. The brand owner
gets notified via outbox event ``moderation.brand_match.created`` so
they can take down the listing through their dashboard (separate
sprint — out of scope here).

Public API
──────────
  classify(text) -> list[dict]
      Returns brand matches found in text. Each entry:
      {brand_id, brand_name, policy, matched_variant}

Integrated with apps/moderation/service.py — every moderate() call
augments its decision with brand-match context. Above 0 brand
matches, severity is bumped to 'high'.
"""
from __future__ import annotations

import logging
import re

from django.conf import settings
from django.db import models


log = logging.getLogger('micha.brand_registry')


class ProtectedBrand(models.Model):
    """A registered brand that the moderation engine should flag on
    listing creation. Append-only by convention — disable via is_active."""

    POLICY_CHOICES = [
        ('review', 'Route to brand-review queue'),
        ('block',  'Hard-refuse listing creation'),
        ('manual', 'No automatic action — manual review only'),
    ]

    name = models.CharField(max_length=120, unique=True, db_index=True)
    # Lowercase exact-match needles. The canonical name is auto-added
    # by save() so callers don't have to remember.
    variants = models.JSONField(default=list, blank=True)
    owner_email = models.EmailField(blank=True, default='')
    policy = models.CharField(max_length=10, choices=POLICY_CHOICES,
                              default='review')
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'moderation_protected_brand'
        ordering = ['name']

    def __str__(self):
        return f'ProtectedBrand({self.name}, {self.policy})'

    def save(self, *args, **kwargs):
        # Normalise variants — always include lowercased name.
        canonical = (self.name or '').lower().strip()
        existing = [v.lower().strip() for v in (self.variants or []) if v]
        if canonical and canonical not in existing:
            existing.append(canonical)
        # Deduplicate.
        seen = set()
        out = []
        for v in existing:
            if v not in seen:
                seen.add(v)
                out.append(v)
        self.variants = out
        super().save(*args, **kwargs)


# ─── Classifier ──────────────────────────────────────────────────────


# Boundary-aware match. ``\bnike\b`` matches 'nike running' but NOT
# 'nikename' — keeps false positives down on common substrings.
def _compile_pattern(variant: str) -> re.Pattern:
    return re.compile(r'\b' + re.escape(variant) + r'\b', re.IGNORECASE)


def classify(text: str) -> list:
    """Return a list of brand matches found in ``text``.

    Each match: {'brand_id', 'brand_name', 'policy', 'matched_variant'}.
    """
    if not text:
        return []
    out = []
    try:
        for brand in ProtectedBrand.objects.filter(is_active=True).iterator(chunk_size=200):
            for variant in (brand.variants or []):
                v = variant.lower().strip()
                if not v:
                    continue
                if _compile_pattern(v).search(text):
                    out.append({
                        'brand_id': brand.pk,
                        'brand_name': brand.name,
                        'policy': brand.policy,
                        'matched_variant': v,
                    })
                    break  # one match per brand is enough
    except Exception:
        log.exception('brand_registry: classify failed')
    return out


def has_block_match(matches: list) -> bool:
    return any(m.get('policy') == 'block' for m in (matches or []))
