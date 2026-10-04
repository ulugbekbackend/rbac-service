from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from rbac.models import Role

User = get_user_model()


class UserRoleShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "display_name"]


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_active", "date_joined", "roles"]
        read_only_fields = ["username", "date_joined"]

    def get_roles(self, user) -> list[dict]:
        return UserRoleShortSerializer([ur.role for ur in user.user_roles.all()], many=True).data


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), many=True, required=False, write_only=True
    )

    class Meta:
        model = User
        fields = ["id", "username", "password", "email", "first_name", "last_name", "role_ids"]

    def validate(self, attrs):
        user = User(**{k: v for k, v in attrs.items() if k not in ("password", "role_ids")})
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "is_active", "password"]

    def validate_password(self, value):
        validate_password(value, self.instance)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)
