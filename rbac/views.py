from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import AuditLog, Permission, Role, RolePermission, UserPermission, UserRole
from .permissions import MissingPermission, require_permission
from .serializers import (
    AuditLogSerializer,
    BulkCheckAccessSerializer,
    CheckAccessQuerySerializer,
    OverrideInputSerializer,
    PermissionIdsSerializer,
    PermissionSerializer,
    RoleDetailSerializer,
    RoleIdsSerializer,
    RoleSerializer,
    UserPermissionSerializer,
    UserRoleSerializer,
)

User = get_user_model()


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    permission_classes = [require_permission("roles.manage")]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("permissions")
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RoleDetailSerializer
        if self.action == "add_permissions":
            return PermissionIdsSerializer
        return RoleSerializer

    def perform_update(self, serializer):
        role = serializer.save()
        services.invalidate_role_users(role.id)

    def perform_destroy(self, instance):
        # user_roles.role is PROTECT, so a role assigned in the meantime still can't be deleted
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("Rol foydalanuvchilarga biriktirilgan, avval ularni olib tashlang")

    @extend_schema(responses=RoleDetailSerializer)
    @action(detail=True, methods=["post"], url_path="permissions")
    def add_permissions(self, request, pk=None):
        role = self.get_object()
        serializer = PermissionIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission=p) for p in serializer.validated_data["permission_ids"]],
                ignore_conflicts=True,
            )
            services.invalidate_role_users(role.id)

        role = Role.objects.prefetch_related("permissions").get(pk=role.pk)
        return Response(RoleDetailSerializer(role).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"permissions/(?P<permission_id>\d+)")
    def remove_permission(self, request, pk=None, permission_id=None):
        role = self.get_object()
        with transaction.atomic():
            deleted, _ = RolePermission.objects.filter(role=role, permission_id=permission_id).delete()
            if not deleted:
                raise NotFound()
            services.invalidate_role_users(role.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [require_permission("permissions.manage")]

    @extend_schema(parameters=[OpenApiParameter("module", str, description="Masalan: loans")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        module = self.request.query_params.get("module")
        if module:
            qs = qs.filter(module=module)
        return qs

    def perform_update(self, serializer):
        permission = serializer.save()
        services.invalidate_permission_users(permission.id)

    @transaction.atomic
    def perform_destroy(self, instance):
        services.invalidate_permission_users(instance.id)
        instance.delete()


def _ensure_can_manage_or_self(request, user_id):
    if request.user.id == user_id:
        return
    if not services.has_permission(request.user.id, "roles.manage"):
        raise MissingPermission("roles.manage")


class UserRolesView(APIView):
    @extend_schema(responses=UserRoleSerializer(many=True))
    def get(self, request, user_id):
        _ensure_can_manage_or_self(request, user_id)
        user = get_object_or_404(User, pk=user_id)
        user_roles = UserRole.objects.filter(user=user).select_related("role")
        return Response(UserRoleSerializer(user_roles, many=True).data)

    @extend_schema(request=RoleIdsSerializer, responses=UserRoleSerializer(many=True))
    def post(self, request, user_id):
        if not services.has_permission(request.user.id, "roles.manage"):
            raise MissingPermission("roles.manage")
        user = get_object_or_404(User, pk=user_id)
        serializer = RoleIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.assign_roles(user, serializer.validated_data["role_ids"], actor=request.user)
        user_roles = UserRole.objects.filter(user=user).select_related("role")
        return Response(UserRoleSerializer(user_roles, many=True).data, status=status.HTTP_201_CREATED)


class UserRoleDetailView(APIView):
    permission_classes = [require_permission("roles.manage")]

    @extend_schema(responses={204: None})
    def delete(self, request, user_id, role_id):
        user = get_object_or_404(User, pk=user_id)
        role = get_object_or_404(Role, pk=role_id)
        if not services.revoke_role(user, role, actor=request.user):
            raise NotFound("Foydalanuvchida bu rol yo'q")
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserPermissionsView(APIView):
    @extend_schema(
        responses=inline_serializer(
            "UserEffectivePermissions",
            {
                "user_id": serializers.IntegerField(),
                "is_super_admin": serializers.BooleanField(),
                "permissions": serializers.ListField(child=serializers.CharField()),
            },
        )
    )
    def get(self, request, user_id):
        _ensure_can_manage_or_self(request, user_id)
        get_object_or_404(User, pk=user_id)
        data = services.get_user_permissions(user_id)
        return Response({"user_id": user_id, **data})


class UserOverridesView(APIView):
    permission_classes = [require_permission("roles.manage")]

    @extend_schema(responses=UserPermissionSerializer(many=True))
    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        overrides = UserPermission.objects.filter(user=user).select_related("permission")
        return Response(UserPermissionSerializer(overrides, many=True).data)

    @extend_schema(request=OverrideInputSerializer, responses=UserPermissionSerializer)
    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        serializer = OverrideInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        override = services.set_override(
            user,
            serializer.validated_data["permission_id"],
            serializer.validated_data["is_denied"],
            actor=request.user,
        )
        return Response(UserPermissionSerializer(override).data, status=status.HTTP_201_CREATED)


class UserOverrideDetailView(APIView):
    permission_classes = [require_permission("roles.manage")]

    @extend_schema(responses={204: None})
    def delete(self, request, user_id, permission_id):
        user = get_object_or_404(User, pk=user_id)
        permission = get_object_or_404(Permission, pk=permission_id)
        if not services.remove_override(user, permission, actor=request.user):
            raise NotFound("Bu permission uchun override yo'q")
        return Response(status=status.HTTP_204_NO_CONTENT)


def _resolve_target_user(request, user_id):
    if user_id is None or user_id == request.user.id:
        return request.user.id
    if not services.has_permission(request.user.id, "users.view_access"):
        raise MissingPermission("users.view_access")
    get_object_or_404(User, pk=user_id)
    return user_id


class CheckAccessView(APIView):
    @extend_schema(
        parameters=[CheckAccessQuerySerializer],
        responses=inline_serializer(
            "CheckAccessResponse",
            {
                "user_id": serializers.IntegerField(),
                "permission": serializers.CharField(),
                "has_access": serializers.BooleanField(),
            },
        ),
    )
    def get(self, request):
        params = CheckAccessQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        user_id = _resolve_target_user(request, params.validated_data.get("user_id"))
        permission = params.validated_data["permission"]
        return Response(
            {
                "user_id": user_id,
                "permission": permission,
                "has_access": services.has_permission(user_id, permission),
            }
        )


class BulkCheckAccessView(APIView):
    @extend_schema(
        request=BulkCheckAccessSerializer,
        responses=inline_serializer(
            "BulkCheckAccessResponse",
            {
                "user_id": serializers.IntegerField(),
                "results": serializers.DictField(child=serializers.BooleanField()),
            },
        ),
    )
    def post(self, request):
        serializer = BulkCheckAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = _resolve_target_user(request, serializer.validated_data.get("user_id"))
        results = services.check_many(user_id, serializer.validated_data["permissions"])
        return Response({"user_id": user_id, "results": results})


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [require_permission("roles.manage")]

    @extend_schema(parameters=[OpenApiParameter("user_id", int)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = AuditLog.objects.select_related("role", "permission")
        user_id = self.request.query_params.get("user_id")
        if user_id and user_id.isdigit():
            qs = qs.filter(target_user_id=user_id)
        return qs
