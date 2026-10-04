import pytest

from rbac.models import Role

URL = "/api/v1/rbac/roles"


@pytest.mark.django_db
class TestRoles:
    def test_requires_auth(self, client):
        assert client.get(URL).status_code == 401

    def test_requires_roles_manage(self, make_user, client_for):
        response = client_for(make_user()).get(URL)
        assert response.status_code == 403
        assert response.json() == {
            "error": "forbidden",
            "message": "Ushbu amal uchun ruxsat yo'q",
            "required_permission": "roles.manage",
        }

    def test_list_is_paginated(self, admin_client):
        response = admin_client.get(URL)
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert "results" in response.json()

    def test_trailing_slash_also_works(self, admin_client):
        assert admin_client.get(URL + "/").status_code == 200

    def test_create(self, admin_client):
        response = admin_client.post(URL, {"name": "manager", "display_name": "Menejer"}, format="json")
        assert response.status_code == 201
        assert Role.objects.filter(name="manager").exists()

    def test_create_duplicate_name(self, admin_client):
        response = admin_client.post(URL, {"name": "admin", "display_name": "Dup"}, format="json")
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"
        assert "name" in response.json()["details"]

    def test_retrieve_with_permissions(self, admin_client, make_role):
        role = make_role("operator", "loans.view", "users.view")
        response = admin_client.get(f"{URL}/{role.id}")
        assert response.status_code == 200
        assert {p["codename"] for p in response.json()["permissions"]} == {"loans.view", "users.view"}

    def test_retrieve_not_found(self, admin_client):
        response = admin_client.get(f"{URL}/9999")
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"

    def test_update(self, admin_client, make_role):
        role = make_role("viewer")
        response = admin_client.patch(f"{URL}/{role.id}", {"display_name": "Kuzatuvchi"}, format="json")
        assert response.status_code == 200
        role.refresh_from_db()
        assert role.display_name == "Kuzatuvchi"

    def test_delete_unused(self, admin_client, make_role):
        role = make_role("temp")
        assert admin_client.delete(f"{URL}/{role.id}").status_code == 204
        assert not Role.objects.filter(pk=role.pk).exists()

    def test_delete_assigned_role_returns_conflict(self, admin_client, make_role, make_user):
        role = make_role("operator")
        make_user(role)
        response = admin_client.delete(f"{URL}/{role.id}")
        assert response.status_code == 409
        assert response.json()["error"] == "conflict"
        assert Role.objects.filter(pk=role.pk).exists()


@pytest.mark.django_db
class TestRolePermissions:
    def test_attach_permissions(self, admin_client, make_role, perm):
        role = make_role("manager")
        p1, p2 = perm("loans.approve"), perm("loans.reject")
        response = admin_client.post(
            f"{URL}/{role.id}/permissions", {"permission_ids": [p1.id, p2.id, p1.id]}, format="json"
        )
        assert response.status_code == 200
        assert set(role.permissions.values_list("codename", flat=True)) == {"loans.approve", "loans.reject"}

    def test_attach_is_idempotent(self, admin_client, make_role, perm):
        role = make_role("manager", "loans.approve")
        p = perm("loans.approve")
        response = admin_client.post(f"{URL}/{role.id}/permissions", {"permission_ids": [p.id]}, format="json")
        assert response.status_code == 200
        assert role.permissions.count() == 1

    def test_attach_unknown_permission(self, admin_client, make_role):
        role = make_role("manager")
        response = admin_client.post(f"{URL}/{role.id}/permissions", {"permission_ids": [999]}, format="json")
        assert response.status_code == 400

    def test_attach_empty_list(self, admin_client, make_role):
        role = make_role("manager")
        response = admin_client.post(f"{URL}/{role.id}/permissions", {"permission_ids": []}, format="json")
        assert response.status_code == 400

    def test_detach_permission(self, admin_client, make_role, perm):
        role = make_role("manager", "loans.approve")
        p = perm("loans.approve")
        assert admin_client.delete(f"{URL}/{role.id}/permissions/{p.id}").status_code == 204
        assert role.permissions.count() == 0

    def test_detach_not_attached(self, admin_client, make_role, perm):
        role = make_role("manager")
        p = perm("loans.approve")
        assert admin_client.delete(f"{URL}/{role.id}/permissions/{p.id}").status_code == 404
