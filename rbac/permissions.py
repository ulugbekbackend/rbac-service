from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .services import has_permission


class MissingPermission(PermissionDenied):
    default_detail = "Ushbu amal uchun ruxsat yo'q"
    default_code = "forbidden"

    def __init__(self, permission):
        super().__init__()
        self.required_permission = permission


def require_permission(codename):
    """
    Usage: permission_classes = [require_permission("loans.approve")]
    """

    class HasPermission(BasePermission):
        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            if not has_permission(request.user.id, codename):
                raise MissingPermission(codename)
            return True

    HasPermission.__name__ = f"HasPermission[{codename}]"
    return HasPermission
