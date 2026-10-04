import pytest

from rbac.models import AuditLog, UserRole


def url(user_id, suffix="roles"):
    return f"/api/v1/rbac/users/{user_id}/{suffix}"


@pytest.mark.django_db
class TestUserRoles:
    def test_assign_roles(self, admin_client, admin_user, make_user, make_role):
        user = make_user()
        r1, r2 = make_role("manager"), make_role("operator")
        response = admin_client.post(url(user.id), {"role_ids": [r1.id, r2.id]}, format="json")
        assert response.status_code == 201
        assert {r["role"]["name"] for r in response.json()} == {"manager", "operator"}
        assert UserRole.objects.get(user=user, role=r1).assigned_by == admin_user
        assert AuditLog.objects.filter(target_user=user, action="role_assigned").count() == 2

    def test_assign_twice_does_not_duplicate(self, admin_client, make_user, make_role):
        role = make_role("manager")
        user = make_user(role)
        admin_client.post(url(user.id), {"role_ids": [role.id]}, format="json")
        assert UserRole.objects.filter(user=user).count() == 1

    def test_assign_unknown_role(self, admin_client, make_user):
        response = admin_client.post(url(make_user().id), {"role_ids": [999]}, format="json")
        assert response.status_code == 400

    def test_assign_to_unknown_user(self, admin_client, make_role):
        role = make_role("manager")
        assert admin_client.post(url(9999), {"role_ids": [role.id]}, format="json").status_code == 404

    def test_assign_without_permission(self, make_user, make_role, client_for):
        role = make_role("manager")
        user = make_user()
        response = client_for(user).post(url(user.id), {"role_ids": [role.id]}, format="json")
        assert response.status_code == 403

    def test_list_roles(self, admin_client, make_user, make_role):
        user = make_user(make_role("manager"))
        response = admin_client.get(url(user.id))
        assert response.status_code == 200
        assert [r["role"]["name"] for r in response.json()] == ["manager"]

    def test_user_can_see_own_roles(self, make_user, make_role, client_for):
        user = make_user(make_role("viewer"))
        assert client_for(user).get(url(user.id)).status_code == 200

    def test_user_cannot_see_others_roles(self, make_user, client_for):
        other = make_user()
        assert client_for(make_user()).get(url(other.id)).status_code == 403

    def test_revoke_role(self, admin_client, make_user, make_role):
        role = make_role("manager")
        user = make_user(role)
        assert admin_client.delete(url(user.id, f"roles/{role.id}")).status_code == 204
        assert not UserRole.objects.filter(user=user).exists()
        assert AuditLog.objects.filter(target_user=user, action="role_revoked").exists()

    def test_revoke_not_assigned(self, admin_client, make_user, make_role):
        role = make_role("manager")
        assert admin_client.delete(url(make_user().id, f"roles/{role.id}")).status_code == 404

    def test_effective_permissions(self, admin_client, make_user, make_role):
        user = make_user(
            make_role("a", "loans.view", "loans.approve"),
            make_role("b", "loans.view", "reports.export"),
        )
        response = admin_client.get(url(user.id, "permissions"))
        assert response.status_code == 200
        assert response.json() == {
            "user_id": user.id,
            "is_super_admin": False,
            "permissions": ["loans.approve", "loans.view", "reports.export"],
        }


@pytest.mark.django_db
class TestOverrides:
    def test_grant_override(self, admin_client, make_user, perm):
        user = make_user()
        p = perm("reports.export")
        response = admin_client.post(url(user.id, "permission-overrides"), {"permission_id": p.id}, format="json")
        assert response.status_code == 201
        assert admin_client.get(url(user.id, "permissions")).json()["permissions"] == ["reports.export"]

    def test_deny_override_beats_role(self, admin_client, make_user, make_role, perm):
        user = make_user(make_role("manager", "loans.approve", "loans.view"))
        p = perm("loans.approve")
        admin_client.post(
            url(user.id, "permission-overrides"), {"permission_id": p.id, "is_denied": True}, format="json"
        )
        assert admin_client.get(url(user.id, "permissions")).json()["permissions"] == ["loans.view"]
        assert AuditLog.objects.filter(target_user=user, action="permission_denied").exists()

    def test_list_and_remove_override(self, admin_client, make_user, perm):
        user = make_user()
        p = perm("reports.export")
        admin_client.post(url(user.id, "permission-overrides"), {"permission_id": p.id}, format="json")
        assert len(admin_client.get(url(user.id, "permission-overrides")).json()) == 1
        assert admin_client.delete(url(user.id, f"permission-overrides/{p.id}")).status_code == 204
        assert admin_client.get(url(user.id, "permissions")).json()["permissions"] == []

    def test_remove_missing_override(self, admin_client, make_user, perm):
        p = perm("reports.export")
        assert admin_client.delete(url(make_user().id, f"permission-overrides/{p.id}")).status_code == 404


@pytest.mark.django_db
def test_audit_log_list(admin_client, make_user, make_role):
    user = make_user()
    role = make_role("manager")
    admin_client.post(url(user.id), {"role_ids": [role.id]}, format="json")
    response = admin_client.get("/api/v1/rbac/audit-logs", {"user_id": user.id})
    assert response.status_code == 200
    assert response.json()["results"][0]["action"] == "role_assigned"
    assert response.json()["results"][0]["role"] == "manager"
