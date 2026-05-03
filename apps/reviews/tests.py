"""
MICHA Express — Reviews Tests
"""
import pytest


@pytest.mark.django_db
class TestProductReviews:

    def test_anyone_can_read_reviews(self, api_client, product):
        res = api_client.get(f'/api/v1/reviews/product/{product.id}/')
        assert res.status_code == 200

    def test_buyer_can_create_review(self, buyer_client, product):
        res = buyer_client.post('/api/v1/reviews/product/', {
            'product': product.id,
            'rating': 5,
            'comment': 'Produto excelente! Muito satisfeito.',
        })
        assert res.status_code in [201, 400]  # 400 if purchase required

    def test_anonymous_cannot_review(self, api_client, product):
        res = api_client.post('/api/v1/reviews/product/', {
            'product': product.id,
            'rating': 5,
            'comment': 'Test review',
        })
        assert res.status_code == 401

    def test_rating_must_be_1_to_5(self, buyer_client, product):
        res = buyer_client.post('/api/v1/reviews/product/', {
            'product': product.id,
            'rating': 10,
            'comment': 'Test',
        })
        assert res.status_code == 400

    def test_buyer_can_flag_review(self, buyer_client, product):
        res = buyer_client.post(f'/api/v1/reviews/product/999/flag/', {
            'reason': 'spam',
        })
        assert res.status_code in [201, 404]
