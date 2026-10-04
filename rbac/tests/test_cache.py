import pytest
from django.core.cache import cache

from rbac import services

CHECK_URL = "/api/v1/rbac/check-access"


def has_access(client, codename):
    return client.get(CHECK_URL, {"permission": codename}).json()["has_access"]


@pytest.mark.django_db(transaction=True)
class TestCacheInvalidation:
    def test_permissions_are_cached(self, make_user, make_role, django_assert_num_queries):
        user = make_user(make_role("manager", "loans.approve"))
        services.get_user_permissions(user.id)
        assert cache.get(services.cache_key(user.id)) is not None
        with django_assert_num_queries(0):
            assert services.has_permission(user.id, "loans.approve")

    def test_attach_permission_to_role(self, admin_client, make_user, make_role, perm, client_for):
        role = make_role("manager")
        client = client_for(make_user(role))
        assert has_access(client, "loans.approve") is False

        p = perm("loans.approve")
        admin_client.post(f"/api/v1/rbac/roles/{role.id}/permissions", {"permission_ids": [p.id]}, format="json")
        assert has_access(client, "loans.approve") is True

    def test_detach_permission_from_role(self, admin_client, make_user, make_role, perm, client_for):
        role = make_role("manager", "loans.approve")
        client = client_for(make_user(role))
        assert has_access(client, "loans.approve") is True

        admin_client.delete(f"/api/v1/rbac/roles/{role.id}/permissions/{perm('loans.approve').id}")
        assert has_access(client, "loans.approve") is False

    def test_assign_and_revoke_role(self, admin_client, make_user, make_role, client_for):
        role = make_role("manager", "loans.approve")
        user = make_user()
        client = client_for(user)
        assert has_access(client, "loans.approve") is False

        admin_client.post(f"/api/v1/rbac/users/{user.id}/roles", {"role_ids": [role.id]}, format="json")
        assert has_access(client, "loans.approve") is True

        admin_client.delete(f"/api/v1/rbac/users/{user.id}/roles/{role.id}")
        assert has_access(client, "loans.approve") is False

    def test_delete_permission(self, admin_client, make_user, make_role, perm, client_for):
        client = client_for(make_user(make_role("manager", "loans.approve")))
        assert has_access(client, "loans.approve") is True

        admin_client.delete(f"/api/v1/rbac/permissions/{perm('loans.approve').id}")
        assert has_access(client, "loans.approve") is False

    def test_toggle_super_admin(self, admin_client, make_user, make_role, client_for):
        role = make_role("manager")
        client = client_for(make_user(role))
        assert has_access(client, "reports.export") is False

        admin_client.patch(f"/api/v1/rbac/roles/{role.id}", {"is_super_admin": True}, format="json")
        assert has_access(client, "reports.export") is True

    def test_role_removed_then_deleted(self, admin_client, make_user, make_role, client_for):
        role = make_role("manager", "loans.approve")
        user = make_user(role)
        client = client_for(user)
        assert has_access(client, "loans.approve") is True

        admin_client.delete(f"/api/v1/rbac/users/{user.id}/roles/{role.id}")
        assert admin_client.delete(f"/api/v1/rbac/roles/{role.id}").status_code == 204
        assert has_access(client, "loans.approve") is False

    def test_override_change(self, admin_client, make_user, make_role, perm, client_for):
        user = make_user(make_role("manager", "loans.approve"))
        client = client_for(user)
        assert has_access(client, "loans.approve") is True

        p = perm("loans.approve")
        admin_client.post(
            f"/api/v1/rbac/users/{user.id}/permission-overrides",
            {"permission_id": p.id, "is_denied": True},
            format="json",
        )
        assert has_access(client, "loans.approve") is False
