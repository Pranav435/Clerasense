"""
API endpoint tests – verifies all REST endpoints return correct structure.
"""


class TestHealthEndpoint:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "clerasense"


class TestAuthEndpoints:
    def test_register_success(self, client):
        resp = client.post("/api/auth/register", json={
            "email": "newdoc@example.com",
            "password": "SecurePass1",
            "full_name": "Dr. New",
            "license_number": "NEW-001",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert "token" in data
        assert data["doctor"]["email"] == "newdoc@example.com"

    def test_register_missing_fields(self, client):
        resp = client.post("/api/auth/register", json={"email": "x@x.com"})
        assert resp.status_code == 400

    def test_login_success(self, client):
        # Register first
        client.post("/api/auth/register", json={
            "email": "logindoc@example.com",
            "password": "Pass1234",
            "full_name": "Dr. Login",
            "license_number": "LOGIN-001",
        })
        resp = client.post("/api/auth/login", json={
            "email": "logindoc@example.com",
            "password": "Pass1234",
        })
        assert resp.status_code == 200
        assert "token" in resp.get_json()

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={
            "email": "logindoc@example.com",
            "password": "WrongPass",
        })
        assert resp.status_code == 401

    def test_protected_route_no_token(self, client):
        resp = client.get("/api/drugs/")
        assert resp.status_code == 401


class TestDrugEndpoints:
    def test_list_drugs(self, client, auth_headers):
        resp = client.get("/api/drugs/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "drugs" in data
        assert len(data["drugs"]) >= 1

    def test_get_drug_by_id(self, client, auth_headers):
        resp = client.get("/api/drugs/1", headers=auth_headers)
        assert resp.status_code == 200
        drug = resp.get_json()["drug"]
        assert drug["generic_name"] == "Metformin"
        # Must include source citation
        assert drug["source"] is not None
        assert "authority" in drug["source"]

    def test_get_drug_not_found(self, client, auth_headers):
        resp = client.get("/api/drugs/9999", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_drug_by_name(self, client, auth_headers):
        resp = client.get("/api/drugs/by-name/metformin", headers=auth_headers)
        assert resp.status_code == 200
        drug = resp.get_json()["drug"]
        assert drug["generic_name"] == "Metformin"
        assert "indications" in drug
        assert "safety_warnings" in drug

    def test_drug_details_have_sources(self, client, auth_headers):
        resp = client.get("/api/drugs/1", headers=auth_headers)
        drug = resp.get_json()["drug"]
        # Every section must have source references
        for indication in drug.get("indications", []):
            assert indication["source"] is not None
        for warning in drug.get("safety_warnings", []):
            assert warning["source"] is not None

    def test_search_drugs(self, client, auth_headers):
        resp = client.get("/api/drugs/?q=metf", headers=auth_headers)
        assert resp.status_code == 200
        drugs = resp.get_json()["drugs"]
        assert any(d["generic_name"] == "Metformin" for d in drugs)


class TestComparisonEndpoint:
    def test_compare_two_drugs(self, client, auth_headers):
        resp = client.post("/api/comparison/", headers=auth_headers, json={
            "drug_names": ["Metformin", "Lisinopril"]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["comparison"]) == 2
        assert "disclaimer" in data

    def test_compare_too_few(self, client, auth_headers):
        resp = client.post("/api/comparison/", headers=auth_headers, json={
            "drug_names": ["Metformin"]
        })
        assert resp.status_code == 400

    def test_compare_too_many(self, client, auth_headers):
        resp = client.post("/api/comparison/", headers=auth_headers, json={
            "drug_names": ["A", "B", "C", "D", "E"]
        })
        assert resp.status_code == 400


class TestSafetyEndpoint:
    def test_safety_check(self, client, auth_headers):
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Metformin"],
            "context": {}
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "safety_warnings" in data
        assert "disclaimer" in data
        assert len(data["safety_warnings"]) >= 1

    def test_safety_pregnancy_alert(self, client, auth_headers):
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Lisinopril"],
            "context": {"pregnancy": True}
        })
        data = resp.get_json()
        assert len(data["context_alerts"]) >= 1
        assert any(a["alert_type"] == "pregnancy" for a in data["context_alerts"])

    def test_safety_empty_drugs(self, client, auth_headers):
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": [],
        })
        assert resp.status_code == 400


class TestPricingEndpoint:
    def test_pricing_lookup(self, client, auth_headers):
        resp = client.get("/api/pricing/Metformin", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["drug"] == "Metformin"
        assert "pricing" in data
        assert "reimbursement" in data
        assert "disclaimer" in data

    def test_pricing_not_found(self, client, auth_headers):
        resp = client.get("/api/pricing/NonExistentDrug", headers=auth_headers)
        assert resp.status_code == 404
