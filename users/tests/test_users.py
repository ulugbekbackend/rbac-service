import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from rbac.models import AuditLog, UserRole

User = get_user_model()
URL = "/api/v1/users"


@pytest.fixture
def staff(make_user, make_role):
    role = make_role("hr", "users.view", "users.create", "users.update", "users.delete")
    return make_user(role, username="hr")


@pytest.fixture
def staff_client(staff, client_for):
    return client_for(staff)


@pytest.mark.django_db
class TestUserList:
    def test_requires_auth(self, client):
        assert client.get(URL).status_code == 401

    def test_requires_users_view(self, make_user, client_for):
        response = client_for(make_user()).get(URL)
        assert response.status_code == 403
        assert response.json()["required_permission"] == "users.view"

    def test_list_with_roles(self, staff_client, make_user, make_role):
        make_user(make_role("operator"), username="ali")
        response = staff_client.get(URL)
        assert response.status_code == 200
        users = {u["username"]: u for u in response.json()["results"]}
        assert [r["name"] for r in users["ali"]["roles"]] == ["operator"]
        assert "password" not in users["ali"]

    def test_search(self, staff_client, make_user):
        make_user(username="vali")
        make_user(username="sardor")
        response = staff_client.get(URL, {"search": "val"})
        assert [u["username"] for u in response.json()["results"]] == ["vali"]

    def test_retrieve(self, staff_client, make_user):
        user = make_user(username="ali")
        response = staff_client.get(f"{URL}/{user.id}")
        assert response.status_code == 200
        assert response.json()["username"] == "ali"

    def test_options_request(self, make_user, client_for):
        assert client_for(make_user()).options(URL).status_code == 200

    def test_retrieve_not_found(self, staff_client):
        assert staff_client.get(f"{URL}/9999").status_code == 404


@pytest.mark.django_db
class TestUserCreate:
    def test_create_with_roles(self, staff_client, staff, make_role):
        role = make_role("operator", "loans.view")
        response = staff_client.post(
            URL,
            {"username": "ali", "password": "Kuchli-parol-123", "email": "ali@example.com", "role_ids": [role.id]},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["roles"][0]["name"] == "operator"
        assert "password" not in response.json()

        user = User.objects.get(username="ali")
        assert user.check_password("Kuchli-parol-123")
        assert UserRole.objects.get(user=user).assigned_by == staff
        assert AuditLog.objects.filter(target_user=user, action="role_assigned").exists()

    def test_created_user_can_login_and_use_role(self, staff_client, make_role):
        role = make_role("operator", "loans.view")
        staff_client.post(URL, {"username": "ali", "password": "Kuchli-parol-123", "role_ids": [role.id]}, format="json")

        client = APIClient()
        token = client.post("/api/v1/auth/token/", {"username": "ali", "password": "Kuchli-parol-123"}).json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert client.get("/api/v1/rbac/check-access", {"permission": "loans.view"}).json()["has_access"] is True
        assert client.post("/api/v1/loans/1/approve").status_code == 403

    def test_weak_password(self, staff_client):
        response = staff_client.post(URL, {"username": "ali", "password": "123"}, format="json")
        assert response.status_code == 400
        assert "password" in response.json()["details"]

    def test_duplicate_username(self, staff_client, make_user):
        make_user(username="ali")
        response = staff_client.post(URL, {"username": "ali", "password": "Kuchli-parol-123"}, format="json")
        assert response.status_code == 400
        assert "username" in response.json()["details"]

    def test_unknown_role(self, staff_client):
        response = staff_client.post(
            URL, {"username": "ali", "password": "Kuchli-parol-123", "role_ids": [999]}, format="json"
        )
        assert response.status_code == 400
        assert not User.objects.filter(username="ali").exists()

    def test_requires_users_create(self, make_user, make_role, client_for):
        client = client_for(make_user(make_role("viewer", "users.view")))
        response = client.post(URL, {"username": "ali", "password": "Kuchli-parol-123"}, format="json")
        assert response.status_code == 403
        assert response.json()["required_permission"] == "users.create"


@pytest.mark.django_db
class TestUserUpdateDelete:
    def test_partial_update(self, staff_client, make_user):
        user = make_user()
        response = staff_client.patch(f"{URL}/{user.id}", {"first_name": "Ali"}, format="json")
        assert response.status_code == 200
        assert response.json()["first_name"] == "Ali"

    def test_change_password(self, staff_client, make_user):
        user = make_user()
        staff_client.patch(f"{URL}/{user.id}", {"password": "Yangi-parol-456"}, format="json")
        user.refresh_from_db()
        assert user.check_password("Yangi-parol-456")

    def test_weak_password_on_update(self, staff_client, make_user):
        user = make_user()
        response = staff_client.patch(f"{URL}/{user.id}", {"password": "123"}, format="json")
        assert response.status_code == 400
        assert "password" in response.json()["details"]

    def test_username_is_read_only(self, staff_client, make_user):
        user = make_user(username="ali")
        staff_client.patch(f"{URL}/{user.id}", {"username": "boshqa"}, format="json")
        user.refresh_from_db()
        assert user.username == "ali"

    def test_cannot_deactivate_self(self, staff_client, staff):
        response = staff_client.patch(f"{URL}/{staff.id}", {"is_active": False}, format="json")
        assert response.status_code == 400

    def test_delete_deactivates(self, staff_client, make_user):
        user = make_user()
        assert staff_client.delete(f"{URL}/{user.id}").status_code == 204
        user.refresh_from_db()
        assert user.is_active is False

    def test_deactivated_user_cannot_login(self, staff_client, make_user):
        user = make_user(username="ali")
        user.set_password("Kuchli-parol-123")
        user.save()
        staff_client.delete(f"{URL}/{user.id}")
        response = APIClient().post("/api/v1/auth/token/", {"username": "ali", "password": "Kuchli-parol-123"})
        assert response.status_code == 401

    def test_cannot_delete_self(self, staff_client, staff):
        assert staff_client.delete(f"{URL}/{staff.id}").status_code == 400

    def test_requires_users_delete(self, make_user, make_role, client_for):
        client = client_for(make_user(make_role("viewer", "users.view")))
        target = make_user()
        assert client.delete(f"{URL}/{target.id}").status_code == 403


@pytest.mark.django_db
class TestMe:
    def test_me(self, make_user, make_role, client_for):
        user = make_user(make_role("operator", "loans.view", "users.view"), username="ali")
        response = client_for(user).get("/api/v1/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["username"] == "ali"
        assert body["user"]["roles"][0]["name"] == "operator"
        assert body["is_super_admin"] is False
        assert body["permissions"] == ["loans.view", "users.view"]

    def test_me_requires_auth(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401
