from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from rbac import services
from rbac.permissions import require_permission

from .serializers import UserCreateSerializer, UserSerializer, UserUpdateSerializer

User = get_user_model()


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_map = {
        "list": "users.view",
        "retrieve": "users.view",
        "create": "users.create",
        "update": "users.update",
        "partial_update": "users.update",
        "destroy": "users.delete",
    }

    def get_permissions(self):
        codename = self.permission_map.get(self.action)
        if codename is None:
            # OPTIONS (action="metadata") and similar — just require a logged-in user
            return super().get_permissions()
        return [require_permission(codename)()]

    def get_queryset(self):
        qs = User.objects.order_by("id").prefetch_related("user_roles__role")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    @extend_schema(parameters=[OpenApiParameter("search", str, description="username yoki email bo'yicha")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=UserCreateSerializer, responses={201: UserSerializer})
    def create(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        roles = data.pop("role_ids", [])

        with transaction.atomic():
            user = User.objects.create_user(**data)
            if roles:
                services.assign_roles(user, roles, actor=request.user)

        return Response(UserSerializer(self.get_queryset().get(pk=user.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=UserUpdateSerializer, responses=UserSerializer)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        user = self.get_object()
        serializer = UserUpdateSerializer(user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        if user.pk == request.user.pk and serializer.validated_data.get("is_active") is False:
            raise ValidationError({"is_active": ["O'zingizni nofaol qila olmaysiz"]})
        serializer.save()
        return Response(UserSerializer(self.get_queryset().get(pk=user.pk)).data)

    @extend_schema(request=UserUpdateSerializer, responses=UserSerializer)
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(description="Userni bazadan o'chirmaydi, faqat nofaol qiladi (audit tarixi saqlanadi)")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError({"detail": ["O'zingizni o'chira olmaysiz"]})
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class MeView(APIView):
    @extend_schema(
        responses=inline_serializer(
            "Me",
            {
                "user": UserSerializer(),
                "is_super_admin": serializers.BooleanField(),
                "permissions": serializers.ListField(child=serializers.CharField()),
            },
        )
    )
    def get(self, request):
        user = User.objects.prefetch_related("user_roles__role").get(pk=request.user.pk)
        return Response({"user": UserSerializer(user).data, **services.get_user_permissions(user.pk)})
