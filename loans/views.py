from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from rbac.permissions import require_permission

loan_response = inline_serializer(
    "LoanActionResponse", {"loan_id": serializers.IntegerField(), "status": serializers.CharField()}
)


@extend_schema(request=None, responses=loan_response)
@api_view(["POST"])
@permission_classes([require_permission("loans.approve")])
def approve_loan(request, loan_id):
    return Response({"loan_id": loan_id, "status": "approved"})


@extend_schema(request=None, responses=loan_response)
@api_view(["POST"])
@permission_classes([require_permission("loans.reject")])
def reject_loan(request, loan_id):
    return Response({"loan_id": loan_id, "status": "rejected"})
