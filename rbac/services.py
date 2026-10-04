from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from .models import AuditLog, RolePermission, UserPermission, UserRole


def cache_key(user_id):
    return f"user:{user_id}:permissions"


def _load_permissions(user_id):
    roles = UserRole.objects.filter(user_id=user_id).select_related("role")
    is_super_admin = any(ur.role.is_super_admin for ur in roles)

    codenames = set(
        RolePermission.objects.filter(role__user_roles__user_id=user_id)
        .values_list("permission__codename", flat=True)
    )
    for codename, is_denied in UserPermission.objects.filter(user_id=user_id).values_list(
        "permission__codename", "is_denied"
    ):
        if is_denied:
            codenames.discard(codename)
        else:
            codenames.add(codename)

    return {"is_super_admin": is_super_admin, "permissions": sorted(codenames)}


def get_user_permissions(user_id):
    key = cache_key(user_id)
    data = cache.get(key)
    if data is None:
        data = _load_permissions(user_id)
        cache.set(key, data, settings.PERMISSIONS_CACHE_TTL)
    return data


def has_permission(user_id, codename):
    return check_many(user_id, [codename])[codename]


def check_many(user_id, codenames):
    data = get_user_permissions(user_id)
    if data["is_super_admin"]:
        return {c: True for c in codenames}
    granted = set(data["permissions"])
    return {c: c in granted for c in codenames}


def invalidate_users(user_ids):
    keys = [cache_key(uid) for uid in set(user_ids)]
    if keys:
        transaction.on_commit(lambda: cache.delete_many(keys))


def invalidate_role_users(role_id):
    invalidate_users(UserRole.objects.filter(role_id=role_id).values_list("user_id", flat=True))


def invalidate_permission_users(permission_id):
    via_roles = UserRole.objects.filter(role__permissions__id=permission_id).values_list("user_id", flat=True)
    via_overrides = UserPermission.objects.filter(permission_id=permission_id).values_list("user_id", flat=True)
    invalidate_users(list(via_roles) + list(via_overrides))


@transaction.atomic
def assign_roles(user, roles, actor):
    existing = set(UserRole.objects.filter(user=user).values_list("role_id", flat=True))
    new_roles = [r for r in roles if r.id not in existing]
    UserRole.objects.bulk_create(UserRole(user=user, role=r, assigned_by=actor) for r in new_roles)
    AuditLog.objects.bulk_create(
        AuditLog(actor=actor, action=AuditLog.Action.ROLE_ASSIGNED, target_user=user, role=r)
        for r in new_roles
    )
    if new_roles:
        invalidate_users([user.id])
    return new_roles


@transaction.atomic
def revoke_role(user, role, actor):
    deleted, _ = UserRole.objects.filter(user=user, role=role).delete()
    if deleted:
        AuditLog.objects.create(actor=actor, action=AuditLog.Action.ROLE_REVOKED, target_user=user, role=role)
        invalidate_users([user.id])
    return bool(deleted)


@transaction.atomic
def set_override(user, permission, is_denied, actor):
    override, _ = UserPermission.objects.update_or_create(
        user=user, permission=permission, defaults={"is_denied": is_denied, "granted_by": actor}
    )
    action = AuditLog.Action.PERMISSION_DENIED if is_denied else AuditLog.Action.PERMISSION_GRANTED
    AuditLog.objects.create(actor=actor, action=action, target_user=user, permission=permission)
    invalidate_users([user.id])
    return override


@transaction.atomic
def remove_override(user, permission, actor):
    deleted, _ = UserPermission.objects.filter(user=user, permission=permission).delete()
    if deleted:
        AuditLog.objects.create(
            actor=actor, action=AuditLog.Action.OVERRIDE_REMOVED, target_user=user, permission=permission
        )
        invalidate_users([user.id])
    return bool(deleted)
