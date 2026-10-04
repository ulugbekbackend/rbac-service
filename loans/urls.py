from django.urls import path

from . import views

urlpatterns = [
    path("<int:loan_id>/approve", views.approve_loan, name="loan-approve"),
    path("<int:loan_id>/reject", views.reject_loan, name="loan-reject"),
]
