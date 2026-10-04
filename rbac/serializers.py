from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AuditLog, Permission, Role, UserPermission, UserRole

User = get_user_model()


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "codename", "display_name", "module", "description", "created_at", "updated_at"]
        read_only_fields = ["module", "created_at", "updated_at"]
        # uniqueness is checked in validate_codename after normalizing
        extra_kwargs = {"codename": {"validators": []}}

    def validate_codename(self, value):
        value = value.strip().lower()
        parts = value.split(".")
        if len(parts) < 2 or not all(parts):
            raise serializers.ValidationError("Format: <module>.<action>, masalan loans.approve")

        qs = Permission.objects.filter(codename=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu codename allaqachon mavjud")
        return value


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "display_name", "description", "is_super_admin", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class RoleDetailSerializer(RoleSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)

    class Meta(RoleSerializer.Meta):
        fields = RoleSerializer.Meta.fields + ["permissions"]


class _IdListField(serializers.ListField):
    child = serializers.IntegerField(min_value=1)

    def __init__(self, **kwargs):
        kwargs.setdefault("allow_empty", False)
        super().__init__(**kwargs)


def _fetch_by_ids(model, ids, label):
    ids = list(dict.fromkeys(ids))
    objects = list(model.objects.filter(id__in=ids))
    missing = sorted(set(ids) - {o.id for o in objects})
    if missing:
        raise serializers.ValidationError(f"{label} topilmadi: {missing}")
    return objects


class PermissionIdsSerializer(serializers.Serializer):
    permission_ids = _IdListField()

    def validate_permission_ids(self, value):
        return _fetch_by_ids(Permission, value, "Permission")


class RoleIdsSerializer(serializers.Serializer):
    role_ids = _IdListField()

    def validate_role_ids(self, value):
        return _fetch_by_ids(Role, value, "Rol")


class UserRoleSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    assigned_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = UserRole
        fields = ["role", "assigned_by", "assigned_at"]


class UserPermissionSerializer(serializers.ModelSerializer):
    permission = serializers.SlugRelatedField(slug_field="codename", read_only=True)

    class Meta:
        model = UserPermission
        fields = ["permission", "is_denied", "granted_by", "created_at"]


class OverrideInputSerializer(serializers.Serializer):
    permission_id = serializers.PrimaryKeyRelatedField(queryset=Permission.objects.all())
    is_denied = serializers.BooleanField(default=False)


class CheckAccessQuerySerializer(serializers.Serializer):
    permission = serializers.CharField(max_length=100)
    user_id = serializers.IntegerField(min_value=1, required=False)


class BulkCheckAccessSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1, required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=False, max_length=100
    )


class AuditLogSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="name", read_only=True)
    permission = serializers.SlugRelatedField(slug_field="codename", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "action", "target_user", "role", "permission", "created_at"]
