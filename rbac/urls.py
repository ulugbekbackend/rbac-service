from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.trailing_slash = "/?"
router.register("roles", views.RoleViewSet, basename="role")
router.register("permissions", views.PermissionViewSet, basename="permission")

urlpatterns = [
    path("users/<int:user_id>/roles", views.UserRolesView.as_view(), name="user-roles"),
    path("users/<int:user_id>/roles/<int:role_id>", views.UserRoleDetailView.as_view(), name="user-role-detail"),
    path("users/<int:user_id>/permissions", views.UserPermissionsView.as_view(), name="user-permissions"),
    path("users/<int:user_id>/permission-overrides", views.UserOverridesView.as_view(), name="user-overrides"),
    path(
        "users/<int:user_id>/permission-overrides/<int:permission_id>",
        views.UserOverrideDetailView.as_view(),
        name="user-override-detail",
    ),
    path("check-access", views.CheckAccessView.as_view(), name="check-access"),
    path("check-access/bulk", views.BulkCheckAccessView.as_view(), name="check-access-bulk"),
    path("audit-logs", views.AuditLogListView.as_view(), name="audit-logs"),
] + router.urls
