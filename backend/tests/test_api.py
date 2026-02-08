"""
API endpoint tests – verifies all REST endpoints return correct structure.
Covers auth, drug CRUD, comparisons, safety (incl. FAERS), prescription verification, and pricing (incl. NADAC).
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

    def test_drug_dosage_includes_overdose_underdose(self, client, auth_headers):
        """Dosage guidelines must include overdose_info and underdose_info fields."""
        resp = client.get("/api/drugs/1", headers=auth_headers)
        drug = resp.get_json()["drug"]
        assert "dosage_guidelines" in drug
        assert len(drug["dosage_guidelines"]) >= 1
        dg = drug["dosage_guidelines"][0]
        assert "overdose_info" in dg
        assert "underdose_info" in dg
        assert dg["overdose_info"] is not None
        assert "OVERDOSE" in dg["overdose_info"]
        assert dg["underdose_info"] is not None
        assert "UNDERDOSE" in dg["underdose_info"]

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

    def test_comparison_includes_overdose_underdose(self, client, auth_headers):
        """Compared drugs include overdose_info and underdose_info in dosage guidelines."""
        resp = client.post("/api/comparison/", headers=auth_headers, json={
            "drug_names": ["Metformin", "Lisinopril"]
        })
        for drug in resp.get_json()["comparison"]:
            assert "dosage_guidelines" in drug
            for dg in drug["dosage_guidelines"]:
                assert "overdose_info" in dg
                assert "underdose_info" in dg


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
# PRESCRIPTION VERIFICATION
# ════════════════════════════════════════════

class TestPrescriptionEndpoint:
    """Tests for the /api/prescription/verify endpoint."""

    def test_prescription_verify_empty_text(self, client, auth_headers):
        """Empty OCR text returns 400."""
        resp = client.post("/api/prescription/verify", headers=auth_headers, json={
            "ocr_text": ""
        })
        assert resp.status_code == 400

    def test_prescription_verify_missing_body(self, client, auth_headers):
        """Missing ocr_text field returns 400."""
        resp = client.post("/api/prescription/verify", headers=auth_headers, json={})
        assert resp.status_code == 400

    def test_prescription_verify_too_long(self, client, auth_headers):
        """Excessively long text returns 400."""
        resp = client.post("/api/prescription/verify", headers=auth_headers, json={
            "ocr_text": "x" * 20000
        })
        assert resp.status_code == 400

    def test_prescription_verify_no_auth(self, client):
        """Prescription endpoint requires authentication."""
        resp = client.post("/api/prescription/verify", json={
            "ocr_text": "Metformin 500mg twice daily"
        })
        assert resp.status_code == 401

    def test_prescription_verify_success(self, client, auth_headers, monkeypatch):
        """Successful verification returns expected structure (mocked AI)."""
        # Mock the AI calls in prescription_service
        import app.services.prescription_service as ps

        mock_extracted = {
            "medications": [
                {"drug_name": "Metformin", "dosage": "500mg", "frequency": "twice daily",
                 "route": "oral", "duration": "30 days", "quantity": "60"}
            ],
            "patient_info": {"name": "Test Patient", "age": "55", "gender": "Male", "weight": None},
            "diagnosis": "Type 2 Diabetes",
            "prescriber": "Dr. Smith",
            "date": "2025-01-01",
            "additional_instructions": "Take with food"
        }

        mock_ai_analysis = {
            "overall_assessment": "VERIFIED",
            "assessment_summary": "Prescription appears appropriate for Type 2 Diabetes.",
            "medication_analysis": [
                {
                    "drug_name": "Metformin",
                    "found_in_database": True,
                    "drug_class": "Biguanide",
                    "prescribed_dosage": "500mg twice daily",
                    "standard_dosage_info": "500-2000mg daily",
                    "dosage_assessment": "appropriate",
                    "indication_match": "appropriate for stated diagnosis",
                    "indication_details": "Metformin is first-line for Type 2 Diabetes.",
                    "key_warnings": ["Lactic acidosis risk"],
                    "required_monitoring": ["Renal function (eGFR)", "B12 levels annually"],
                    "dosage_instructions": "Take 500mg twice daily with meals.",
                    "special_populations": "Contraindicated with eGFR <30"
                }
            ],
            "interaction_alerts": [],
            "warnings_summary": ["Monitor renal function before and during treatment"],
            "required_scans_and_tests": [
                {"test_name": "eGFR", "reason": "Assess renal function", "timing": "Before starting", "related_drug": "Metformin"}
            ],
            "missing_information": [],
            "recommendations": ["Monitor HbA1c every 3 months"]
        }

        monkeypatch.setattr(ps, "extract_prescription_data", lambda text: mock_extracted)
        monkeypatch.setattr(ps, "_run_ai_verification", lambda *a: mock_ai_analysis)

        resp = client.post("/api/prescription/verify", headers=auth_headers, json={
            "ocr_text": "Patient: Test Patient, Age 55, Male\nDr. Smith\nDate: 2025-01-01\nDx: Type 2 Diabetes\nRx: Metformin 500mg BID x30days #60\nSig: Take with food"
        })
        assert resp.status_code == 200
        data = resp.get_json()

        # Check top-level structure
        assert "extracted_data" in data
        assert "drugs_found" in data
        assert "drugs_not_found" in data
        assert "safety_warnings" in data
        assert "interaction_alerts" in data
        assert "dosage_guidelines" in data
        assert "ai_analysis" in data
        assert "disclaimer" in data

        # Metformin should be found
        assert "Metformin" in data["drugs_found"]

        # AI analysis structure
        ai = data["ai_analysis"]
        assert ai["overall_assessment"] == "VERIFIED"
        assert len(ai["medication_analysis"]) == 1
        assert ai["medication_analysis"][0]["drug_name"] == "Metformin"

    def test_prescription_verify_with_interactions(self, client, auth_headers, monkeypatch):
        """Prescription with interacting drugs surfaces DB interaction alerts."""
        import app.services.prescription_service as ps

        mock_extracted = {
            "medications": [
                {"drug_name": "Metformin", "dosage": "500mg", "frequency": "BID",
                 "route": "oral", "duration": None, "quantity": None},
                {"drug_name": "Lisinopril", "dosage": "10mg", "frequency": "daily",
                 "route": "oral", "duration": None, "quantity": None},
            ],
            "patient_info": {"name": None, "age": None, "gender": None, "weight": None},
            "diagnosis": "HTN + T2DM",
            "prescriber": None,
            "date": None,
            "additional_instructions": None,
        }

        mock_ai = {
            "overall_assessment": "VERIFIED WITH CONCERNS",
            "assessment_summary": "Both drugs found. Interaction noted.",
            "medication_analysis": [],
            "interaction_alerts": [],
            "warnings_summary": [],
            "required_scans_and_tests": [],
            "missing_information": [],
            "recommendations": [],
        }

        monkeypatch.setattr(ps, "extract_prescription_data", lambda text: mock_extracted)
        monkeypatch.setattr(ps, "_run_ai_verification", lambda *a: mock_ai)

        resp = client.post("/api/prescription/verify", headers=auth_headers, json={
            "ocr_text": "Metformin 500mg BID, Lisinopril 10mg daily"
        })
        assert resp.status_code == 200
        data = resp.get_json()

        # Both drugs found
        assert "Metformin" in data["drugs_found"]
        assert "Lisinopril" in data["drugs_found"]

        # DB interaction alerts should be surfaced
        assert len(data["interaction_alerts"]) >= 1

        # Safety warnings from DB
        assert len(data["safety_warnings"]) >= 1

    def test_prescription_verify_unknown_drug(self, client, auth_headers, monkeypatch):
        """Unknown drug in prescription appears in drugs_not_found."""
        import app.services.prescription_service as ps

        mock_extracted = {
            "medications": [
                {"drug_name": "Metformin", "dosage": "500mg", "frequency": "BID",
                 "route": "oral", "duration": None, "quantity": None},
                {"drug_name": "FakeDrugXYZ", "dosage": "100mg", "frequency": "daily",
                 "route": "oral", "duration": None, "quantity": None},
            ],
            "patient_info": {"name": None, "age": None, "gender": None, "weight": None},
            "diagnosis": None,
            "prescriber": None,
            "date": None,
            "additional_instructions": None,
        }

        mock_ai = {
            "overall_assessment": "REQUIRES REVIEW",
            "assessment_summary": "One drug not found in database.",
            "medication_analysis": [],
            "interaction_alerts": [],
            "warnings_summary": [],
            "required_scans_and_tests": [],
            "missing_information": [],
            "recommendations": [],
        }

        monkeypatch.setattr(ps, "extract_prescription_data", lambda text: mock_extracted)
        monkeypatch.setattr(ps, "_run_ai_verification", lambda *a: mock_ai)

        resp = client.post("/api/prescription/verify", headers=auth_headers, json={
            "ocr_text": "Metformin 500mg BID, FakeDrugXYZ 100mg daily"
        })
        assert resp.status_code == 200
        data = resp.get_json()

        assert "Metformin" in data["drugs_found"]
        assert "FakeDrugXYZ" in data["drugs_not_found"]


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

    def test_pricing_reimbursement_us_schemes(self, client, auth_headers):
        """US reimbursement should return Medicare, Medicaid, 340B, and Extra Help."""
        resp = client.get("/api/pricing/Metformin?country=US", headers=auth_headers)
        data = resp.get_json()
        reimb = data["reimbursement"]
        assert data["reimbursement_country"] == "US"
        scheme_names = [r["scheme_name"] for r in reimb]
        assert "Medicare Part D" in scheme_names
        assert "Medicaid" in scheme_names
        assert "340B Drug Pricing Program" in scheme_names

    def test_pricing_reimbursement_india_schemes(self, client, auth_headers):
        """India reimbursement should return PMBJP, NLEM, PMJAY, CGHS, ESI."""
        resp = client.get("/api/pricing/Metformin?country=IN", headers=auth_headers)
        data = resp.get_json()
        reimb = data["reimbursement"]
        assert data["reimbursement_country"] == "IN"
        scheme_names = [r["scheme_name"] for r in reimb]
        assert any("Jan" in s or "PMBJP" in s for s in scheme_names)
        assert any("NLEM" in s for s in scheme_names)

    def test_pricing_reimbursement_has_source(self, client, auth_headers):
        """Every reimbursement entry must have a verified source with URL."""
        resp = client.get("/api/pricing/Metformin?country=US", headers=auth_headers)
        reimb = resp.get_json()["reimbursement"]
        for r in reimb:
            assert "source" in r and r["source"] is not None
            assert r["source"]["authority"]
            assert r["source"]["url"]
            assert r["source"]["document_title"]

    def test_pricing_reimbursement_has_coverage_status(self, client, auth_headers):
        """Each reimbursement entry should have coverage_status and coverage_note."""
        resp = client.get("/api/pricing/Metformin?country=US", headers=auth_headers)
        reimb = resp.get_json()["reimbursement"]
        valid_statuses = {"likely_covered", "may_be_covered", "check_formulary", "inpatient_only"}
        for r in reimb:
            assert r.get("coverage_status") in valid_statuses
            assert r.get("coverage_note")

    def test_pricing_reimbursement_countries_endpoint(self, client, auth_headers):
        """GET /pricing/reimbursement/countries should return supported countries."""
        resp = client.get("/api/pricing/reimbursement/countries", headers=auth_headers)
        assert resp.status_code == 200
        countries = resp.get_json()["countries"]
        codes = [c["code"] for c in countries]
        assert "US" in codes
        assert "IN" in codes
        assert "GB" in codes
# ════════════════════════════════════════════

class TestBrandEndpoints:
    """Tests for the /drugs/<id>/brands endpoints."""

    def test_get_drug_brands(self, client, auth_headers):
        """GET brands for Metformin returns seeded US brand products."""
        resp = client.get("/api/drugs/1/brands", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "brands" in data
        assert data["generic_name"] == "Metformin"
        assert data["country"] == "US"
        assert len(data["brands"]) == 3

    def test_brand_product_structure(self, client, auth_headers):
        """Each brand product dict contains all required fields."""
        resp = client.get("/api/drugs/1/brands", headers=auth_headers)
        brands = resp.get_json()["brands"]
        required_fields = [
            "id", "brand_name", "medicine_name", "manufacturer", "dosage_form",
            "strength", "route", "is_combination", "active_ingredients",
            "product_type", "source_url", "source_authority", "market_country",
        ]
        for brand in brands:
            for field in required_fields:
                assert field in brand, f"Missing field: {field}"

    def test_brand_medicine_name(self, client, auth_headers):
        """Medicine name is the full prescribable name (brand + strength + form)."""
        resp = client.get("/api/drugs/1/brands", headers=auth_headers)
        brands = resp.get_json()["brands"]
        brand_map = {b["brand_name"]: b for b in brands}
        # Glucophage medicine name should include strength and dosage form
        glucophage = brand_map["Glucophage"]
        assert "Glucophage" in glucophage["medicine_name"]
        assert "500 mg" in glucophage["medicine_name"]
        # Janumet medicine name should reflect combo
        janumet = brand_map["Janumet"]
        assert "Janumet" in janumet["medicine_name"]

    def test_brand_pure_vs_combination(self, client, auth_headers):
        """Verify pure and combination brands are correctly tagged."""
        resp = client.get("/api/drugs/1/brands", headers=auth_headers)
        brands = resp.get_json()["brands"]
        brand_map = {b["brand_name"]: b for b in brands}

        # Glucophage = pure metformin
        assert brand_map["Glucophage"]["is_combination"] is False
        assert len(brand_map["Glucophage"]["active_ingredients"]) == 1

        # Janumet = combination (metformin + sitagliptin)
        assert brand_map["Janumet"]["is_combination"] is True
        assert len(brand_map["Janumet"]["active_ingredients"]) == 2

    def test_brand_pricing_fields(self, client, auth_headers):
        """Brand products include NADAC pricing data."""
        resp = client.get("/api/drugs/1/brands", headers=auth_headers)
        brands = resp.get_json()["brands"]
        brand_map = {b["brand_name"]: b for b in brands}
        glucophage = brand_map["Glucophage"]
        assert glucophage["nadac_per_unit"] is not None
        assert glucophage["nadac_per_unit"] > 0
        assert glucophage["ndc"] is not None
        assert glucophage["approximate_cost"] is not None

    def test_brand_source_authority(self, client, auth_headers):
        """Brand products have verified source information."""
        resp = client.get("/api/drugs/1/brands", headers=auth_headers)
        brands = resp.get_json()["brands"]
        for b in brands:
            assert b["source_authority"] == "FDA"
            assert b["source_url"] is not None
            assert b["source_url"].startswith("https://")

    def test_brands_not_found_drug(self, client, auth_headers):
        """Non-existent drug returns 404."""
        resp = client.get("/api/drugs/9999/brands", headers=auth_headers)
        assert resp.status_code == 404

    def test_brands_no_auth(self, client):
        """Brands endpoint requires authentication."""
        resp = client.get("/api/drugs/1/brands")
        assert resp.status_code == 401

    # ── Country-filtered brands ──

    def test_brands_country_us_explicit(self, client, auth_headers):
        """Explicitly passing ?country=US returns only US brands."""
        resp = client.get("/api/drugs/1/brands?country=US", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["country"] == "US"
        assert data["country_name"] == "United States"
        assert len(data["brands"]) == 3
        for b in data["brands"]:
            assert b["market_country"] == "US"

    def test_brands_country_india(self, client, auth_headers):
        """Passing ?country=IN returns Indian market brands."""
        resp = client.get("/api/drugs/1/brands?country=IN", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["country"] == "IN"
        assert data["country_name"] == "India"
        assert len(data["brands"]) >= 1
        for b in data["brands"]:
            assert b["market_country"] == "IN"

    def test_brands_india_glycomet(self, client, auth_headers):
        """Seeded Indian brand Glycomet appears correctly."""
        resp = client.get("/api/drugs/1/brands?country=IN", headers=auth_headers)
        brands = resp.get_json()["brands"]
        brand_map = {b["brand_name"]: b for b in brands}
        assert "Glycomet" in brand_map
        g = brand_map["Glycomet"]
        assert g["manufacturer"] == "USV Limited"
        assert g["market_country"] == "IN"
        assert "FAERS" in g["source_authority"]

    def test_brands_country_empty_market(self, client, auth_headers):
        """Country with no seeded brands returns empty list (no crash)."""
        resp = client.get("/api/drugs/1/brands?country=ZZ", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["country"] == "ZZ"
        assert isinstance(data["brands"], list)

    def test_brands_response_has_country_fields(self, client, auth_headers):
        """Response envelope includes country and country_name."""
        resp = client.get("/api/drugs/1/brands?country=IN", headers=auth_headers)
        data = resp.get_json()
        assert "country" in data
        assert "country_name" in data

    # ── Compare brands ──

    def test_compare_brands_success(self, client, auth_headers):
        """Compare two brands returns structured comparison."""
        resp = client.post("/api/drugs/1/brands/compare",
                           headers=auth_headers,
                           json={"brand_ids": [1, 2]})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["generic_name"] == "Metformin"
        assert len(data["brands"]) == 2
        names = {b["brand_name"] for b in data["brands"]}
        assert "Glucophage" in names
        assert "Janumet" in names

    def test_compare_brands_three(self, client, auth_headers):
        """Compare three brands works."""
        resp = client.post("/api/drugs/1/brands/compare",
                           headers=auth_headers,
                           json={"brand_ids": [1, 2, 3]})
        assert resp.status_code == 200
        assert len(resp.get_json()["brands"]) == 3

    def test_compare_brands_too_few(self, client, auth_headers):
        """Comparing fewer than 2 brands returns 400."""
        resp = client.post("/api/drugs/1/brands/compare",
                           headers=auth_headers,
                           json={"brand_ids": [1]})
        assert resp.status_code == 400

    def test_compare_brands_too_many(self, client, auth_headers):
        """Comparing more than 6 brands returns 400."""
        resp = client.post("/api/drugs/1/brands/compare",
                           headers=auth_headers,
                           json={"brand_ids": [1, 2, 3, 4, 5, 6, 7]})
        assert resp.status_code == 400

    def test_compare_brands_drug_not_found(self, client, auth_headers):
        """Comparing brands for non-existent drug returns 404."""
        resp = client.post("/api/drugs/9999/brands/compare",
                           headers=auth_headers,
                           json={"brand_ids": [1, 2]})
        assert resp.status_code == 404

    def test_compare_brands_invalid_ids(self, client, auth_headers):
        """Brand IDs that don't belong to the drug return 404."""
        resp = client.post("/api/drugs/1/brands/compare",
                           headers=auth_headers,
                           json={"brand_ids": [999, 998]})
        assert resp.status_code == 404

    def test_compare_brands_no_auth(self, client):
        """Compare endpoint requires authentication."""
        resp = client.post("/api/drugs/1/brands/compare",
                           json={"brand_ids": [1, 2]})
        assert resp.status_code == 401
