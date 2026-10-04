from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler

from rbac.permissions import MissingPermission


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, MissingPermission):
        response.data = {
            "error": "forbidden",
            "message": str(exc.detail),
            "required_permission": exc.required_permission,
        }
    elif isinstance(exc, exceptions.ValidationError):
        response.data = {
            "error": "validation_error",
            "message": "So'rov ma'lumotlari noto'g'ri",
            "details": response.data,
        }
    elif isinstance(exc, Http404):
        response.data = {"error": "not_found", "message": "Topilmadi"}
    elif isinstance(exc, exceptions.NotFound):
        message = str(exc.detail) if exc.detail != exceptions.NotFound.default_detail else "Topilmadi"
        response.data = {"error": "not_found", "message": message}
    elif isinstance(exc, exceptions.APIException):
        code = exc.get_codes() if isinstance(exc.get_codes(), str) else exc.default_code
        response.data = {"error": code, "message": _message(exc.detail)}

    return response


def _message(detail):
    # simplejwt returns {"detail": ..., "code": ..., "messages": [{"message": "Token is expired", ...}]}
    if isinstance(detail, dict):
        messages = detail.get("messages")
        if messages and isinstance(messages[0], dict) and "message" in messages[0]:
            return str(messages[0]["message"])
        return str(detail.get("detail", ""))
    return str(detail)
