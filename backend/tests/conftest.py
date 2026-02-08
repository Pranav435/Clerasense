"""
Pytest configuration & fixtures for Clerasense backend tests.

Key design decisions:
  - Uses sqlite:///:memory: for speed and isolation.
  - Patches SQLAlchemy ARRAY → JSON-backed Text before models load
    (SQLite has no ARRAY type).
  - Disables background scheduler & initial ingestion to prevent
    network calls during testing.
  - Seeds complete test data including FAERS + NADAC fields.
"""

import json
import os
import sys
from unittest import mock

import pytest

# ── 1. Ensure backend package is importable ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 2. Set test environment BEFORE anything else ──
os.environ["OPENAI_API_KEY"] = "test-key-not-real"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["EMBEDDING_MODEL_NAME"] = "text-embedding-3-small"
os.environ["APP_ENV"] = "testing"

# ── 3. Patch ARRAY type for SQLite compat BEFORE any model loads ──
import sqlalchemy
import sqlalchemy.types as _sa_types


class _PortableArray(_sa_types.TypeDecorator):
    """Drop-in replacement for ARRAY that stores values as JSON text."""

    impl = _sa_types.Text
    cache_ok = True

    def __init__(self, item_type=None, *args, **kwargs):
        super().__init__()

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value


# Patch BEFORE any model module is imported
sqlalchemy.ARRAY = _PortableArray
_sa_types.ARRAY = _PortableArray

# ── 4. Mock background scheduler so it never runs during tests ──
_noop = lambda *a, **kw: None
mock.patch("app.services.background_scheduler.init_scheduler", _noop).start()
mock.patch("app.services.background_scheduler.run_initial_ingestion", _noop).start()

# ── 5. NOW safe to import application modules ──
from app.main import create_app
from app.database import db as _db
from app.models.models import (
    Doctor, Source, Drug, SafetyWarning, DrugInteraction,
    Indication, DosageGuideline, Pricing, Reimbursement, BrandProduct,
)


# ═══════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════

@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    application = create_app()
    application.config["TESTING"] = True
    application.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    return application


@pytest.fixture(scope="session")
def _setup_db(app):
    """Create all tables once for the test session and seed data."""
    with app.app_context():
        _db.create_all()
        _seed_test_data()
        _db.session.commit()
    yield
    with app.app_context():
        _db.drop_all()


@pytest.fixture
def client(app, _setup_db):
    """Flask test client with database ready."""
    with app.test_client() as c:
        with app.app_context():
            yield c


@pytest.fixture
def auth_headers(client):
    """Register a test doctor and return valid auth headers."""
    with client.application.app_context():
        doc = Doctor.query.filter_by(email="testdoc@example.com").first()
        if not doc:
            client.post("/api/auth/register", json={
                "email": "testdoc@example.com",
                "password": "TestPass123",
                "full_name": "Dr. Test",
                "license_number": "TEST-001",
                "specialization": "Internal Medicine",
            })

    resp = client.post("/api/auth/login", json={
        "email": "testdoc@example.com",
        "password": "TestPass123",
    })
    data = resp.get_json()
    token = data["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ═══════════════════════════════════════════
# SEED DATA  (mirrors real ingestion output)
# ═══════════════════════════════════════════

_FAERS_REACTIONS = json.dumps([
    {"reaction": "NAUSEA", "count": 29316},
    {"reaction": "DIARRHOEA", "count": 27324},
    {"reaction": "BLOOD GLUCOSE INCREASED", "count": 27460},
    {"reaction": "DRUG INEFFECTIVE", "count": 22203},
    {"reaction": "FATIGUE", "count": 20905},
])


def _seed_test_data():
    """Insert complete test data covering all model fields."""
    # ── Sources ──
    src_fda = Source(
        source_id=1, authority="FDA",
        document_title="FDA Drug Label – Metformin",
        publication_year=2024,
        url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test",
        effective_date="2024-08-21",
    )
    src_cms = Source(
        source_id=2, authority="CMS",
        document_title="NADAC Weekly Price – Metformin",
        publication_year=2024,
        url="https://data.medicaid.gov/dataset/dfa2ab14",
    )
    src_fda2 = Source(
        source_id=3, authority="FDA",
        document_title="FDA Drug Label – Lisinopril",
        publication_year=2023,
        url="https://example.com/lisinopril",
    )
    _db.session.add_all([src_fda, src_cms, src_fda2])
    _db.session.flush()

    # ── Drugs ──
    drug1 = Drug(
        id=1, generic_name="Metformin",
        brand_names=["Glucophage", "Janumet"],
        drug_class="Biguanide",
        mechanism_of_action="Decreases hepatic glucose production.",
        source_id=1,
    )
    drug2 = Drug(
        id=2, generic_name="Lisinopril",
        brand_names=["Zestril", "Prinivil"],
        drug_class="ACE Inhibitor",
        mechanism_of_action="Inhibits angiotensin-converting enzyme.",
        source_id=3,
    )
    _db.session.add_all([drug1, drug2])
    _db.session.flush()

    # ── Indications ──
    _db.session.add(Indication(drug_id=1, approved_use="Type 2 diabetes mellitus.", source_id=1))
    _db.session.add(Indication(drug_id=2, approved_use="Hypertension.", source_id=3))

    # ── Dosage Guidelines ──
    _db.session.add(DosageGuideline(
        drug_id=1, adult_dosage="500mg twice daily",
        renal_adjustment="eGFR <30: Contraindicated",
        overdose_info="OVERDOSE — Lactic acidosis: mortality rate ~50%. Hemodialysis recommended.",
        underdose_info="UNDERDOSE — Subtherapeutic below 1000 mg/day. Risk of poor glycemic control.",
        administration_info="Route: Oral. Available forms: Tablets (500 mg, 850 mg, 1000 mg). Take with meals.",
        source_id=1,
    ))
    _db.session.add(DosageGuideline(
        drug_id=2, adult_dosage="10mg once daily",
        renal_adjustment="CrCl <30: reduce dose",
        overdose_info="OVERDOSE — Severe hypotension, hyperkalemia. IV saline first-line.",
        underdose_info="UNDERDOSE — Inadequate BP control below 10 mg/day in most adults.",
        administration_info="Route: Oral. Available forms: Tablets (2.5 mg, 5 mg, 10 mg, 20 mg, 40 mg). May be taken with or without food.",
        source_id=3,
    ))

    # ── Safety Warnings (with FAERS data for Metformin) ──
    _db.session.add(SafetyWarning(
        drug_id=1,
        contraindications="Severe renal impairment (eGFR <30 mL/min/1.73 m²).",
        black_box_warnings="Lactic acidosis: a rare but serious metabolic complication.",
        pregnancy_risk="Category B",
        lactation_risk="Compatible with breastfeeding.",
        adverse_event_count=428835,
        adverse_event_serious_count=285519,
        top_adverse_reactions=_FAERS_REACTIONS,
        source_id=1,
    ))
    _db.session.add(SafetyWarning(
        drug_id=2,
        contraindications="History of angioedema with prior ACE inhibitor use.",
        black_box_warnings="Fetal toxicity. Discontinue when pregnancy detected.",
        pregnancy_risk="Category D",
        lactation_risk="Not recommended during breastfeeding.",
        adverse_event_count=None,
        adverse_event_serious_count=None,
        top_adverse_reactions=None,
        source_id=3,
    ))

    # ── Drug Interactions ──
    _db.session.add(DrugInteraction(
        drug_id=1, interacting_drug="Alcohol", severity="major",
        description="Increases lactic acidosis risk.", source_id=1,
    ))
    _db.session.add(DrugInteraction(
        drug_id=1, interacting_drug="Lisinopril", severity="minor",
        description="May enhance hypoglycemic effect.", source_id=1,
    ))
    _db.session.add(DrugInteraction(
        drug_id=2, interacting_drug="Metformin", severity="minor",
        description="May enhance hypoglycemic effect.", source_id=3,
    ))

    # ── Pricing (with NADAC data for Metformin) ──
    _db.session.add(Pricing(
        drug_id=1,
        approximate_cost="$0.02/EA → ~$0.60–$1.80/month (METFORMIN HCL 500 MG)",
        generic_available=True,
        nadac_per_unit=0.02123,
        nadac_ndc="00228200310",
        nadac_effective_date="2024-12-04",
        nadac_package_description="METFORMIN HCL 500 MG TABLET",
        pricing_source="NADAC",
        source_id=2,
    ))
    _db.session.add(Pricing(
        drug_id=2,
        approximate_cost="$5-$15/month estimated",
        generic_available=True,
        pricing_source="estimate",
        source_id=3,
    ))

    # ── Reimbursement ──
    _db.session.add(Reimbursement(
        drug_id=1, scheme_name="Medicare Part D",
        coverage_notes="Tier 1 preferred generic.", source_id=1,
    ))

    # ── Brand Products ──
    _db.session.add(BrandProduct(
        id=1, drug_id=1,
        brand_name="Glucophage",
        medicine_name="Glucophage 500 mg Tablet, Film Coated",
        manufacturer="Bristol-Myers Squibb",
        ndc="0087-6060-05",
        dosage_form="Tablet, Film Coated",
        strength="500 mg",
        route="Oral",
        is_combination=False,
        active_ingredients=json.dumps(["METFORMIN HYDROCHLORIDE"]),
        product_type="HUMAN PRESCRIPTION DRUG",
        nadac_per_unit=0.02123,
        nadac_unit="EA",
        nadac_effective_date="2024-12-04",
        approximate_cost="$0.0212/EA → ~$0.64–$1.91/month",
        source_url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test-glucophage",
        source_authority="FDA",
        market_country="US",
    ))
    _db.session.add(BrandProduct(
        id=2, drug_id=1,
        brand_name="Janumet",
        medicine_name="Janumet 500 mg / 50 mg Tablet, Film Coated",
        manufacturer="Merck Sharp & Dohme",
        ndc="0006-0575-61",
        dosage_form="Tablet, Film Coated",
        strength="500 mg / 50 mg",
        route="Oral",
        is_combination=True,
        active_ingredients=json.dumps(["METFORMIN HYDROCHLORIDE", "SITAGLIPTIN PHOSPHATE"]),
        product_type="HUMAN PRESCRIPTION DRUG",
        nadac_per_unit=3.45,
        nadac_unit="EA",
        nadac_effective_date="2024-12-04",
        approximate_cost="$3.45/EA → ~$103.50–$310.50/month",
        source_url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test-janumet",
        source_authority="FDA",
        market_country="US",
    ))
    _db.session.add(BrandProduct(
        id=3, drug_id=1,
        brand_name="Metformin Hcl",
        medicine_name="Metformin Hcl 500 mg Tablet",
        manufacturer="Teva Pharmaceuticals",
        ndc="0093-7267-01",
        dosage_form="Tablet",
        strength="500 mg",
        route="Oral",
        is_combination=False,
        active_ingredients=json.dumps(["METFORMIN HYDROCHLORIDE"]),
        product_type="HUMAN PRESCRIPTION DRUG",
        nadac_per_unit=0.01898,
        nadac_unit="EA",
        nadac_effective_date="2024-12-04",
        approximate_cost="$0.0190/EA → ~$0.57–$1.71/month",
        source_url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test-teva",
        source_authority="FDA",
        market_country="US",
    ))
    # Indian market brand
    _db.session.add(BrandProduct(
        id=4, drug_id=1,
        brand_name="Glycomet",
        medicine_name="Glycomet 500 mg Tablet",
        manufacturer="USV Limited",
        ndc="",
        dosage_form="Tablet",
        strength="500 mg",
        route="Oral",
        is_combination=False,
        active_ingredients=json.dumps(["METFORMIN HYDROCHLORIDE"]),
        product_type="",
        source_url="https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:GLYCOMET+AND+occurcountry:IN",
        source_authority="FDA FAERS (IN)",
        market_country="IN",
    ))
