"""
API endpoint tests – verifies all REST endpoints return correct structure.
Covers auth, drug CRUD, comparisons, safety (incl. FAERS), and pricing (incl. NADAC).
"""


class TestHealthEndpoint:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "clerasense"


# ════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════

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

    def test_register_duplicate_email(self, client):
        """Duplicate email returns 409."""
        client.post("/api/auth/register", json={
            "email": "dup@example.com",
            "password": "Pass1234",
            "full_name": "Dr. Dup",
            "license_number": "DUP-001",
        })
        resp = client.post("/api/auth/register", json={
            "email": "dup@example.com",
            "password": "Pass1234",
            "full_name": "Dr. Dup2",
            "license_number": "DUP-002",
        })
        assert resp.status_code == 409

    def test_login_success(self, client):
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


# ════════════════════════════════════════════
# DRUG ENDPOINTS
# ════════════════════════════════════════════

class TestDrugEndpoints:
    def test_list_drugs(self, client, auth_headers):
        resp = client.get("/api/drugs/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "drugs" in data
        assert len(data["drugs"]) >= 2  # Metformin + Lisinopril

    def test_get_drug_by_id(self, client, auth_headers):
        resp = client.get("/api/drugs/1", headers=auth_headers)
        assert resp.status_code == 200
        drug = resp.get_json()["drug"]
        assert drug["generic_name"] == "Metformin"
        # Source citation must be present
        assert drug["source"] is not None
        assert drug["source"]["authority"] == "FDA"

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
        assert "pricing" in drug

    def test_drug_details_have_sources(self, client, auth_headers):
        """Every related record must carry its source citation."""
        resp = client.get("/api/drugs/1", headers=auth_headers)
        drug = resp.get_json()["drug"]
        for indication in drug.get("indications", []):
            assert indication["source"] is not None
        for warning in drug.get("safety_warnings", []):
            assert warning["source"] is not None
        for pricing in drug.get("pricing", []):
            assert pricing["source"] is not None

    def test_search_drugs(self, client, auth_headers):
        resp = client.get("/api/drugs/?q=metf", headers=auth_headers)
        assert resp.status_code == 200
        drugs = resp.get_json()["drugs"]
        assert any(d["generic_name"] == "Metformin" for d in drugs)

    def test_drug_brand_names(self, client, auth_headers):
        resp = client.get("/api/drugs/1", headers=auth_headers)
        drug = resp.get_json()["drug"]
        assert "Glucophage" in drug["brand_names"]

    def test_drug_source_effective_date(self, client, auth_headers):
        """Source must include effective_date when available."""
        resp = client.get("/api/drugs/1", headers=auth_headers)
        source = resp.get_json()["drug"]["source"]
        assert source["effective_date"] == "2024-08-21"


# ════════════════════════════════════════════
# COMPARISON
# ════════════════════════════════════════════

class TestComparisonEndpoint:
    def test_compare_two_drugs(self, client, auth_headers):
        resp = client.post("/api/comparison/", headers=auth_headers, json={
            "drug_names": ["Metformin", "Lisinopril"]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["comparison"]) == 2
        assert "disclaimer" in data
        names = [d["generic_name"] for d in data["comparison"]]
        assert "Metformin" in names
        assert "Lisinopril" in names

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

    def test_comparison_includes_pricing_and_safety(self, client, auth_headers):
        """Compared drugs include safety_warnings and pricing details."""
        resp = client.post("/api/comparison/", headers=auth_headers, json={
            "drug_names": ["Metformin", "Lisinopril"]
        })
        for drug in resp.get_json()["comparison"]:
            assert "safety_warnings" in drug
            assert "pricing" in drug


# ════════════════════════════════════════════
# SAFETY (including FAERS adverse event data)
# ════════════════════════════════════════════

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

    def test_safety_warning_structure(self, client, auth_headers):
        """Safety warnings should include contraindications, black box, and source."""
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Metformin"],
            "context": {}
        })
        warning = resp.get_json()["safety_warnings"][0]
        assert "contraindications" in warning
        assert "black_box_warnings" in warning
        assert "pregnancy_risk" in warning
        assert "lactation_risk" in warning
        assert warning["source"] is not None
        assert warning["source"]["authority"] == "FDA"

    def test_safety_pregnancy_alert(self, client, auth_headers):
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Lisinopril"],
            "context": {"pregnancy": True}
        })
        data = resp.get_json()
        assert len(data["context_alerts"]) >= 1
        assert any(a["alert_type"] == "pregnancy" for a in data["context_alerts"])

    def test_safety_renal_alert(self, client, auth_headers):
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Metformin"],
            "context": {"renal_impairment": True}
        })
        data = resp.get_json()
        assert len(data["context_alerts"]) >= 1
        assert any(a["alert_type"] == "renal_impairment" for a in data["context_alerts"])

    def test_safety_empty_drugs(self, client, auth_headers):
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": [],
        })
        assert resp.status_code == 400

    def test_safety_interaction_alert(self, client, auth_headers):
        """Checking two drugs with a known interaction should surface the alert."""
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Metformin", "Lisinopril"],
            "context": {}
        })
        data = resp.get_json()
        assert "interaction_alerts" in data
        # Metformin ↔ Lisinopril interaction is seeded
        assert len(data["interaction_alerts"]) >= 1

    def test_safety_not_found_drug(self, client, auth_headers):
        """Drugs not in DB are listed in drugs_not_found."""
        resp = client.post("/api/safety/check", headers=auth_headers, json={
            "drug_names": ["Metformin", "SuperFakeDrugXYZ"],
            "context": {}
        })
        data = resp.get_json()
        assert "SuperFakeDrugXYZ" in data["drugs_not_found"]


# ════════════════════════════════════════════
# PRICING (including NADAC data)
# ════════════════════════════════════════════

class TestPricingEndpoint:
    def test_pricing_lookup(self, client, auth_headers):
        resp = client.get("/api/pricing/Metformin", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["drug"] == "Metformin"
        assert "pricing" in data
        assert "reimbursement" in data
        assert "disclaimer" in data
        assert data["generic_available"] is True

    def test_pricing_nadac_fields(self, client, auth_headers):
        """Metformin pricing should include NADAC-specific fields."""
        resp = client.get("/api/pricing/Metformin", headers=auth_headers)
        pricing_list = resp.get_json()["pricing"]
        assert len(pricing_list) >= 1
        p = pricing_list[0]
        assert p["nadac_per_unit"] is not None
        assert p["nadac_per_unit"] > 0
        assert p["nadac_ndc"] is not None
        assert p["nadac_package_description"] is not None
        assert p["pricing_source"] == "NADAC"

    def test_pricing_estimate_drug(self, client, auth_headers):
        """Drug with only estimated pricing should have pricing_source='estimate'."""
        resp = client.get("/api/pricing/Lisinopril", headers=auth_headers)
        pricing_list = resp.get_json()["pricing"]
        assert len(pricing_list) >= 1
        p = pricing_list[0]
        assert p["pricing_source"] == "estimate"
        assert p["nadac_per_unit"] is None

    def test_pricing_not_found(self, client, auth_headers):
        resp = client.get("/api/pricing/NonExistentDrug", headers=auth_headers)
        assert resp.status_code == 404

    def test_pricing_reimbursement(self, client, auth_headers):
        resp = client.get("/api/pricing/Metformin", headers=auth_headers)
        reimb = resp.get_json()["reimbursement"]
        assert len(reimb) >= 1
        assert reimb[0]["scheme_name"] == "Medicare Part D"
