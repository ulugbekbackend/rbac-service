from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from rbac import services
from rbac.models import UserRole

from .models import User


class UserRoleInline(admin.TabularInline):
    model = UserRole
    fk_name = "user"
    extra = 0
    fields = ["role", "assigned_by", "assigned_at"]
    readonly_fields = ["assigned_by", "assigned_at"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserRoleInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        services.invalidate_users([form.instance.id])
