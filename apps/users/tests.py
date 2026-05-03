"""
MICHA Express — User & Auth Tests
"""
import pytest

VALID_USER = {
    'email': 'newuser@test.com',
    'password': 'StrongPass123!',
    'password2': 'StrongPass123!',
    'privacy_consent': True,
    'terms_consent': True,
}

AUTH_FAIL = [400, 401, 403]


@pytest.mark.django_db
class TestRegistration:

    def test_register_valid_user(self, api_client):
        res = api_client.post('/api/v1/auth/register/', VALID_USER)
        assert res.status_code == 201

    def test_register_duplicate_email(self, api_client, buyer):
        data = {**VALID_USER, 'email': 'buyer@test.com'}
        res = api_client.post('/api/v1/auth/register/', data)
        assert res.status_code == 400

    def test_register_weak_password_rejected(self, api_client):
        data = {**VALID_USER, 'email': 'weak@test.com', 'password': '123', 'password2': '123'}
        res = api_client.post('/api/v1/auth/register/', data)
        assert res.status_code == 400

    def test_register_password_mismatch(self, api_client):
        data = {**VALID_USER, 'email': 'mismatch@test.com', 'password2': 'DifferentPass123!'}
        res = api_client.post('/api/v1/auth/register/', data)
        assert res.status_code == 400

    def test_register_requires_terms_consent(self, api_client):
        data = {**VALID_USER, 'email': 'noterms@test.com', 'terms_consent': False}
        res = api_client.post('/api/v1/auth/register/', data)
        assert res.status_code == 400

    def test_register_requires_privacy_consent(self, api_client):
        data = {**VALID_USER, 'email': 'noprivacy@test.com', 'privacy_consent': False}
        res = api_client.post('/api/v1/auth/register/', data)
        assert res.status_code == 400


@pytest.mark.django_db
class TestLogin:

    def test_login_valid_credentials(self, api_client, buyer):
        res = api_client.post('/api/v1/auth/login/', {
            'email': 'buyer@test.com',
            'password': 'TestPass123!',
        })
        assert res.status_code == 200
        assert 'access' in res.data
        assert 'refresh' in res.data

    def test_login_wrong_password(self, api_client, buyer):
        res = api_client.post('/api/v1/auth/login/', {
            'email': 'buyer@test.com',
            'password': 'WrongPassword!',
        })
        assert res.status_code in AUTH_FAIL

    def test_login_nonexistent_user(self, api_client):
        res = api_client.post('/api/v1/auth/login/', {
            'email': 'nobody@test.com',
            'password': 'TestPass123!',
        })
        assert res.status_code in AUTH_FAIL

    def test_login_unverified_email_rejected(self, api_client, db):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(
            email='unverified@test.com',
            password='TestPass123!',
            is_email_verified=False,
        )
        res = api_client.post('/api/v1/auth/login/', {
            'email': 'unverified@test.com',
            'password': 'TestPass123!',
        })
        assert res.status_code in AUTH_FAIL

    def test_login_suspended_user_rejected(self, api_client, db):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(
            email='suspended@test.com',
            password='TestPass123!',
            is_email_verified=True,
            status='suspended',
        )
        res = api_client.post('/api/v1/auth/login/', {
            'email': 'suspended@test.com',
            'password': 'TestPass123!',
        })
        assert res.status_code in AUTH_FAIL

    def test_unauthenticated_cannot_access_profile(self, api_client):
        res = api_client.get('/api/v1/auth/profile/')
        assert res.status_code == 401

    def test_authenticated_can_access_profile(self, buyer_client):
        res = buyer_client.get('/api/v1/auth/profile/')
        assert res.status_code == 200

    def test_logout_returns_success(self, buyer_client, buyer):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(buyer)
        res = buyer_client.post('/api/v1/auth/logout/', {'refresh': str(refresh)})
        assert res.status_code == 200


@pytest.mark.django_db
class TestPasswordSecurity:

    def test_change_password_wrong_old_password(self, buyer_client):
        res = buyer_client.post('/api/v1/auth/change-password/', {
            'old_password': 'WrongPass!',
            'new_password': 'NewStrongPass123!',
            'new_password2': 'NewStrongPass123!',
        })
        assert res.status_code in AUTH_FAIL

    @pytest.mark.skip(reason='Requires email backend — configure SendGrid first')
    def test_forgot_password_valid_email(self, api_client, buyer):
        res = api_client.post('/api/v1/auth/forgot-password/', {
            'email': 'buyer@test.com',
        })
        assert res.status_code == 200

    @pytest.mark.skip(reason='Requires email backend — configure SendGrid first')
    def test_forgot_password_prevents_email_enumeration(self, api_client):
        res = api_client.post('/api/v1/auth/forgot-password/', {
            'email': 'nobody@test.com',
        })
        assert res.status_code == 200
