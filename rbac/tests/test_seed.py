from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from rbac import services
from rbac.models import Permission, Role, UserRole


def seed(**kwargs):
    call_command("seed_rbac", stdout=StringIO(), **kwargs)


@pytest.mark.django_db
class TestSeed:
    def test_creates_defaults(self):
        seed()
        assert set(Role.objects.values_list("name", flat=True)) == {
            "super_admin", "admin", "manager", "operator", "viewer",
        }
        assert Permission.objects.count() == 12
        assert Role.objects.get(name="super_admin").is_super_admin
        assert Role.objects.get(name="admin").permissions.count() == 12
        assert set(Role.objects.get(name="operator").permissions.values_list("codename", flat=True)) == {
            "users.view", "loans.view",
        }

    def test_is_idempotent(self):
        seed()
        seed()
        assert Role.objects.count() == 5
        assert Permission.objects.count() == 12
        assert Role.objects.get(name="manager").permissions.count() == 6

    def test_keeps_changes_made_through_api(self):
        seed()
        manager = Role.objects.get(name="manager")
        manager.display_name = "Bo'lim boshlig'i"
        manager.save()
        manager.permissions.remove(Permission.objects.get(codename="loans.approve"))
        Permission.objects.filter(codename="loans.view").update(display_name="Kreditlar ro'yxati")

        seed()

        manager.refresh_from_db()
        assert manager.display_name == "Bo'lim boshlig'i"
        assert not manager.permissions.filter(codename="loans.approve").exists()
        assert Permission.objects.get(codename="loans.view").display_name == "Kreditlar ro'yxati"

    def test_restores_deleted_role(self):
        seed()
        Role.objects.filter(name="viewer").delete()
        seed()
        assert Role.objects.get(name="viewer").permissions.count() == 3

    def test_admin_option(self, make_user):
        user = make_user(username="boss")
        seed(admin="boss")
        assert UserRole.objects.filter(user=user, role__name="super_admin").exists()
        assert services.has_permission(user.id, "anything.here")

    def test_admin_from_env(self, settings):
        settings.ADMIN_USERNAME = "root"
        settings.ADMIN_PASSWORD = "Kuchli-parol-123"
        seed()
        seed()
        user = get_user_model().objects.get(username="root")
        assert user.is_superuser and user.check_password("Kuchli-parol-123")
        assert UserRole.objects.filter(user=user).count() == 1
        assert services.has_permission(user.id, "anything.here")

    def test_admin_from_env_does_not_touch_existing_user(self, settings, make_user):
        user = make_user(username="root")
        settings.ADMIN_USERNAME = "root"
        settings.ADMIN_PASSWORD = "Kuchli-parol-123"
        seed()
        user.refresh_from_db()
        assert not user.is_superuser
        assert not UserRole.objects.filter(user=user).exists()

    def test_admin_option_unknown_user(self):
        with pytest.raises(CommandError):
            seed(admin="nobody")
