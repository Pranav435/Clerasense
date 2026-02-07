"""
Pytest configuration & fixtures for Clerasense backend tests.
"""

import os
import sys
import pytest

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set test environment variables BEFORE importing app
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
os.environ.setdefault("APP_ENV", "testing")

from app.main import create_app
from app.database import db as _db
from app.models.models import Doctor, Source, Drug, SafetyWarning, DrugInteraction, Indication, DosageGuideline, Pricing, Reimbursement
import bcrypt


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    application = create_app()
    application.config["TESTING"] = True
    application.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    return application


@pytest.fixture(scope="session")
def _setup_db(app):
    """Create all tables once for the test session."""
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
    """Register a test doctor and return auth headers."""
    # Check if doctor already exists
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
    token = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _seed_test_data():
    """Insert minimal test data."""
    src = Source(source_id=1, authority="FDA", document_title="Test FDA Label", publication_year=2023, url="https://example.com")
    _db.session.add(src)
    _db.session.flush()

    drug = Drug(id=1, generic_name="Metformin", brand_names=["Glucophage"], drug_class="Biguanide",
                mechanism_of_action="Decreases hepatic glucose production.", source_id=1)
    _db.session.add(drug)

    drug2 = Drug(id=2, generic_name="Lisinopril", brand_names=["Zestril"], drug_class="ACE Inhibitor",
                 mechanism_of_action="Inhibits ACE.", source_id=1)
    _db.session.add(drug2)
    _db.session.flush()

    _db.session.add(Indication(drug_id=1, approved_use="Type 2 diabetes mellitus.", source_id=1))
    _db.session.add(DosageGuideline(drug_id=1, adult_dosage="500mg twice daily", renal_adjustment="eGFR <30: Contraindicated", source_id=1))
    _db.session.add(SafetyWarning(drug_id=1, contraindications="Severe renal impairment", black_box_warnings="Lactic acidosis risk", pregnancy_risk="Category B", lactation_risk="Compatible", source_id=1))
    _db.session.add(SafetyWarning(drug_id=2, contraindications="History of angioedema", black_box_warnings="Fetal toxicity", pregnancy_risk="Category D", lactation_risk="Not recommended", source_id=1))
    _db.session.add(DrugInteraction(drug_id=1, interacting_drug="Alcohol", severity="major", description="Increases lactic acidosis risk.", source_id=1))
    _db.session.add(DrugInteraction(drug_id=2, interacting_drug="Metformin", severity="minor", description="May enhance hypoglycemic effect.", source_id=1))
    _db.session.add(Pricing(drug_id=1, approximate_cost="$4-30/month", generic_available=True, source_id=1))
    _db.session.add(Reimbursement(drug_id=1, scheme_name="Medicare Part D", coverage_notes="Tier 1 preferred generic.", source_id=1))
