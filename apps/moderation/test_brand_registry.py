"""R4 brand registry tests."""
from __future__ import annotations

import pytest

from apps.moderation.brand_registry import (
    ProtectedBrand, classify, has_block_match,
)
from apps.moderation.service import moderate, ModerationDecision


@pytest.mark.django_db
class TestBrandRegistry:

    def test_save_canonicalises_variants(self):
        b = ProtectedBrand.objects.create(name='Nike', variants=[])
        assert 'nike' in b.variants

    def test_classify_finds_brand(self):
        ProtectedBrand.objects.create(
            name='Apple', variants=['apple', 'iphone'], policy='review',
        )
        matches = classify('Brand new iPhone 15 — Apple original!')
        names = {m['brand_name'] for m in matches}
        assert 'Apple' in names

    def test_word_boundary_avoids_substring(self):
        ProtectedBrand.objects.create(name='Nike', policy='review')
        # 'nikename' should NOT match.
        matches = classify('User nikename has many products')
        assert matches == []

    def test_block_policy_returns_block_decision(self, db):
        ProtectedBrand.objects.create(name='Rolex', policy='block')
        decision = moderate(
            text='Genuine Rolex Submariner replica',
            target_type='product', target_id=42,
        )
        assert decision == ModerationDecision.BLOCK

    def test_review_policy_returns_review_decision(self, db):
        ProtectedBrand.objects.create(name='Samsung', policy='review')
        decision = moderate(
            text='Samsung Galaxy S24 unlocked',
            target_type='product', target_id=43,
        )
        # ContentFlag row written with severity='high'.
        assert decision == ModerationDecision.REVIEW
        from apps.moderation.models import ContentFlag
        flag = ContentFlag.objects.filter(target_id=43).first()
        assert flag is not None
        assert flag.severity == 'high'
        assert 'Brand match' in flag.reason

    def test_no_match_returns_allow(self, db):
        ProtectedBrand.objects.create(name='Nike', policy='block')
        decision = moderate(
            text='Locally made shoes, comfortable for daily wear',
            target_type='product', target_id=44,
        )
        assert decision == ModerationDecision.ALLOW

    def test_has_block_match_helper(self):
        matches = [{'policy': 'review'}, {'policy': 'block'}]
        assert has_block_match(matches) is True
        assert has_block_match([{'policy': 'review'}]) is False
        assert has_block_match([]) is False

    def test_inactive_brand_not_classified(self, db):
        ProtectedBrand.objects.create(name='Nike', is_active=False, policy='block')
        matches = classify('Buy Nike shoes here')
        assert matches == []
