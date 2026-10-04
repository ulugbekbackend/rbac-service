import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from rbac.models import Permission, Role, UserRole


@pytest.fixture(autouse=True)
def _test_settings(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.ADMIN_USERNAME = settings.ADMIN_PASSWORD = ""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(*roles, username=None):
        counter["n"] += 1
        user = get_user_model().objects.create_user(username=username or f"user{counter['n']}", password="x")
        for role in roles:
            UserRole.objects.create(user=user, role=role)
        return user

    return _make


@pytest.fixture
def perm(db):
    def _make(codename):
        return Permission.objects.get_or_create(codename=codename, defaults={"display_name": codename})[0]

    return _make


@pytest.fixture
def make_role(db, perm):
    def _make(name, *codenames, is_super_admin=False):
        role = Role.objects.create(name=name, display_name=name.title(), is_super_admin=is_super_admin)
        role.permissions.add(*[perm(c) for c in codenames])
        return role

    return _make


@pytest.fixture
def client_for():
    def _client(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    return _client


@pytest.fixture
def admin_user(make_user, make_role):
    role = make_role("admin", "roles.manage", "permissions.manage", "users.view_access")
    return make_user(role, username="admin")


@pytest.fixture
def admin_client(admin_user, client_for):
    return client_for(admin_user)
