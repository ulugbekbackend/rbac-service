import pytest

from rbac.models import Permission

URL = "/api/v1/rbac/permissions"


@pytest.mark.django_db
class TestPermissions:
    def test_requires_permissions_manage(self, make_user, client_for):
        response = client_for(make_user()).get(URL)
        assert response.status_code == 403
        assert response.json()["required_permission"] == "permissions.manage"

    def test_list_filter_by_module(self, admin_client, perm):
        perm("loans.approve")
        perm("loans.reject")
        perm("reports.export")
        response = admin_client.get(URL, {"module": "loans"})
        assert response.status_code == 200
        assert {p["codename"] for p in response.json()["results"]} == {"loans.approve", "loans.reject"}

    def test_create_sets_module(self, admin_client):
        response = admin_client.post(URL, {"codename": "Reports.Export", "display_name": "Eksport"}, format="json")
        assert response.status_code == 201
        assert response.json()["codename"] == "reports.export"
        assert response.json()["module"] == "reports"

    def test_create_invalid_codename(self, admin_client):
        response = admin_client.post(URL, {"codename": "export", "display_name": "x"}, format="json")
        assert response.status_code == 400
        assert "codename" in response.json()["details"]

    def test_create_duplicate(self, admin_client, perm):
        perm("loans.approve")
        response = admin_client.post(URL, {"codename": "loans.approve", "display_name": "x"}, format="json")
        assert response.status_code == 400
        assert response.json()["details"]["codename"] == ["Bu codename allaqachon mavjud"]

    def test_create_duplicate_different_case(self, admin_client, perm):
        perm("loans.approve")
        response = admin_client.post(URL, {"codename": " Loans.Approve ", "display_name": "x"}, format="json")
        assert response.status_code == 400
        assert response.json()["details"]["codename"] == ["Bu codename allaqachon mavjud"]
        assert Permission.objects.filter(codename__iexact="loans.approve").count() == 1

    def test_update_codename_to_existing(self, admin_client, perm):
        perm("loans.approve")
        p = perm("loans.reject")
        response = admin_client.patch(f"{URL}/{p.id}", {"codename": "LOANS.APPROVE"}, format="json")
        assert response.status_code == 400

    def test_update_keeps_own_codename(self, admin_client, perm):
        p = perm("loans.approve")
        response = admin_client.put(
            f"{URL}/{p.id}", {"codename": "Loans.Approve", "display_name": "Tasdiqlash"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["codename"] == "loans.approve"

    def test_update(self, admin_client, perm):
        p = perm("loans.approve")
        response = admin_client.patch(f"{URL}/{p.id}", {"display_name": "Tasdiqlash"}, format="json")
        assert response.status_code == 200
        p.refresh_from_db()
        assert p.display_name == "Tasdiqlash"

    def test_delete(self, admin_client, perm):
        p = perm("loans.approve")
        assert admin_client.delete(f"{URL}/{p.id}").status_code == 204
        assert not Permission.objects.filter(pk=p.pk).exists()

    def test_delete_not_found(self, admin_client):
        assert admin_client.delete(f"{URL}/999").status_code == 404
