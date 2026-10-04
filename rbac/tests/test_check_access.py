import pytest

from rbac.models import UserPermission

URL = "/api/v1/rbac/check-access"
BULK_URL = "/api/v1/rbac/check-access/bulk"


@pytest.mark.django_db
class TestCheckAccess:
    def test_requires_auth(self, client):
        assert client.get(URL, {"permission": "loans.approve"}).status_code == 401

    def test_current_user_has_access(self, make_user, make_role, client_for):
        user = make_user(make_role("manager", "loans.approve"))
        response = client_for(user).get(URL, {"permission": "loans.approve"})
        assert response.status_code == 200
        assert response.json() == {"user_id": user.id, "permission": "loans.approve", "has_access": True}

    def test_current_user_without_access(self, make_user, make_role, client_for):
        user = make_user(make_role("operator", "loans.view"))
        response = client_for(user).get(URL, {"permission": "loans.approve"})
        assert response.json()["has_access"] is False

    def test_unknown_permission_is_false(self, make_user, client_for):
        response = client_for(make_user()).get(URL, {"permission": "nothing.here"})
        assert response.json()["has_access"] is False

    def test_permission_param_required(self, make_user, client_for):
        response = client_for(make_user()).get(URL)
        assert response.status_code == 400
        assert "permission" in response.json()["details"]

    def test_access_through_any_of_multiple_roles(self, make_user, make_role, client_for):
        user = make_user(make_role("operator", "loans.view"), make_role("reporter", "reports.export"))
        response = client_for(user).get(URL, {"permission": "reports.export"})
        assert response.json()["has_access"] is True

    def test_super_admin_always_true(self, make_user, make_role, client_for):
        user = make_user(make_role("root", is_super_admin=True))
        response = client_for(user).get(URL, {"permission": "anything.at_all"})
        assert response.json()["has_access"] is True

    def test_denied_override(self, make_user, make_role, perm, client_for):
        user = make_user(make_role("manager", "loans.approve"))
        UserPermission.objects.create(user=user, permission=perm("loans.approve"), is_denied=True)
        assert client_for(user).get(URL, {"permission": "loans.approve"}).json()["has_access"] is False

    def test_granted_override(self, make_user, perm, client_for):
        user = make_user()
        UserPermission.objects.create(user=user, permission=perm("reports.export"))
        assert client_for(user).get(URL, {"permission": "reports.export"}).json()["has_access"] is True

    def test_other_user_requires_view_access(self, make_user, make_role, client_for):
        target = make_user(make_role("manager", "loans.approve"))
        response = client_for(make_user()).get(URL, {"permission": "loans.approve", "user_id": target.id})
        assert response.status_code == 403
        assert response.json()["required_permission"] == "users.view_access"

    def test_other_user_with_view_access(self, admin_client, make_user, make_role):
        target = make_user(make_role("manager", "loans.approve"))
        response = admin_client.get(URL, {"permission": "loans.approve", "user_id": target.id})
        assert response.status_code == 200
        assert response.json() == {"user_id": target.id, "permission": "loans.approve", "has_access": True}

    def test_own_user_id_does_not_need_view_access(self, make_user, client_for):
        user = make_user()
        response = client_for(user).get(URL, {"permission": "loans.approve", "user_id": user.id})
        assert response.status_code == 200

    def test_other_user_not_found(self, admin_client):
        response = admin_client.get(URL, {"permission": "loans.approve", "user_id": 99999})
        assert response.status_code == 404


@pytest.mark.django_db
class TestBulkCheckAccess:
    def test_bulk(self, make_user, make_role, client_for):
        user = make_user(make_role("manager", "loans.approve", "reports.export"))
        response = client_for(user).post(
            BULK_URL, {"permissions": ["loans.approve", "loans.reject", "reports.export"]}, format="json"
        )
        assert response.status_code == 200
        assert response.json() == {
            "user_id": user.id,
            "results": {"loans.approve": True, "loans.reject": False, "reports.export": True},
        }

    def test_bulk_for_other_user(self, admin_client, make_user, make_role):
        target = make_user(make_role("operator", "loans.view"))
        response = admin_client.post(
            BULK_URL, {"user_id": target.id, "permissions": ["loans.view", "loans.approve"]}, format="json"
        )
        assert response.json()["results"] == {"loans.view": True, "loans.approve": False}

    def test_bulk_other_user_forbidden(self, make_user, client_for):
        target = make_user()
        response = client_for(make_user()).post(
            BULK_URL, {"user_id": target.id, "permissions": ["loans.view"]}, format="json"
        )
        assert response.status_code == 403

    def test_bulk_super_admin(self, make_user, make_role, client_for):
        user = make_user(make_role("root", is_super_admin=True))
        response = client_for(user).post(BULK_URL, {"permissions": ["a.b", "c.d"]}, format="json")
        assert response.json()["results"] == {"a.b": True, "c.d": True}

    def test_bulk_empty_list(self, make_user, client_for):
        response = client_for(make_user()).post(BULK_URL, {"permissions": []}, format="json")
        assert response.status_code == 400
