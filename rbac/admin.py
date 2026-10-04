from django.contrib import admin

from . import services
from .models import AuditLog, Permission, Role, RolePermission, UserPermission, UserRole


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ["permission"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "display_name", "is_super_admin", "updated_at"]
    search_fields = ["name", "display_name"]
    inlines = [RolePermissionInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        services.invalidate_role_users(form.instance.id)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ["codename", "display_name", "module"]
    list_filter = ["module"]
    search_fields = ["codename", "display_name"]


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "assigned_by", "assigned_at"]
    list_filter = ["role"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.invalidate_users([obj.user_id])

    def delete_model(self, request, obj):
        services.invalidate_users([obj.user_id])
        super().delete_model(request, obj)


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ["user", "permission", "is_denied", "created_at"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.invalidate_users([obj.user_id])

    def delete_model(self, request, obj):
        services.invalidate_users([obj.user_id])
        super().delete_model(request, obj)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor", "action", "target_user", "role", "permission"]
    list_filter = ["action"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
