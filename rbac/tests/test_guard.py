from datetime import timedelta

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
class TestPermissionGuard:
    def test_forbidden_without_permission(self, make_user, make_role, client_for):
        user = make_user(make_role("operator", "loans.view"))
        response = client_for(user).post("/api/v1/loans/1/approve")
        assert response.status_code == 403
        assert response.json() == {
            "error": "forbidden",
            "message": "Ushbu amal uchun ruxsat yo'q",
            "required_permission": "loans.approve",
        }

    def test_allowed_with_permission(self, make_user, make_role, client_for):
        user = make_user(make_role("manager", "loans.approve"))
        response = client_for(user).post("/api/v1/loans/1/approve")
        assert response.status_code == 200
        assert response.json() == {"loan_id": 1, "status": "approved"}

    def test_each_route_checks_its_own_permission(self, make_user, make_role, client_for):
        client = client_for(make_user(make_role("manager", "loans.approve")))
        response = client.post("/api/v1/loans/1/reject")
        assert response.status_code == 403
        assert response.json()["required_permission"] == "loans.reject"

    def test_unauthenticated(self, client):
        assert client.post("/api/v1/loans/1/approve").status_code == 401

    def test_expired_token_message(self, make_user):
        token = AccessToken.for_user(make_user())
        token.set_exp(lifetime=-timedelta(minutes=1))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post("/api/v1/loans/1/approve")
        assert response.status_code == 401
        assert response.json() == {"error": "token_not_valid", "message": "Token is expired"}

    def test_malformed_token_message(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer abc.def.ghi")
        response = client.post("/api/v1/loans/1/approve")
        assert response.status_code == 401
        assert response.json() == {"error": "token_not_valid", "message": "Token is invalid"}

    def test_works_with_bearer_token(self, make_user, make_role):
        user = make_user(make_role("manager", "loans.approve"))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        assert client.post("/api/v1/loans/5/approve").status_code == 200
