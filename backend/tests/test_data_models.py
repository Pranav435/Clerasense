"""
Data model & source-adapter unit tests.
Validates ORM serialization, NormalizedDrugData dataclass,
NADAC pricing helpers, FAERS data parsing, and source filtering.
"""

import json
import pytest
from dataclasses import asdict

from app.services.drug_sources.base_source import NormalizedDrugData
from app.services.drug_sources.nadac_source import _format_cost_display
from app.services.drug_sources.openfda_source import _clean_text, _extract_severity
from app.models.models import (
    Source, Drug, SafetyWarning, Pricing,
    DrugInteraction, Indication, DosageGuideline,
)


# ═══════════════════════════════════════════
# NormalizedDrugData DATACLASS
# ═══════════════════════════════════════════

class TestNormalizedDrugData:
    def test_defaults(self):
        d = NormalizedDrugData(generic_name="Aspirin")
        assert d.generic_name == "Aspirin"
        assert d.brand_names == []
        assert d.nadac_per_unit is None
        assert d.adverse_event_count is None
        assert d.top_adverse_reactions == []
        assert d.source_year >= 2024

    def test_full_fields(self):
        d = NormalizedDrugData(
            generic_name="Metformin",
            brand_names=["Glucophage"],
            drug_class="Biguanide",
            nadac_per_unit=0.02,
            nadac_ndc="12345",
            adverse_event_count=500000,
            adverse_event_serious_count=300000,
            top_adverse_reactions=[{"reaction": "NAUSEA", "count": 100}],
            source_authority="FDA",
            effective_date="2024-08-21",
        )
        assert d.nadac_per_unit == 0.02
        assert d.adverse_event_count == 500000
        assert d.top_adverse_reactions[0]["reaction"] == "NAUSEA"
        assert d.effective_date == "2024-08-21"

    def test_serializable_to_dict(self):
        d = NormalizedDrugData(generic_name="Test")
        data = asdict(d)
        assert isinstance(data, dict)
        assert data["generic_name"] == "Test"
        # Ensure JSON-serializable
        json.dumps(data)


# ═══════════════════════════════════════════
# NADAC PRICING HELPERS
# ═══════════════════════════════════════════

class TestNADACFormatCostDisplay:
    def test_empty_records(self):
        assert _format_cost_display([], "Metformin") == {}

    def test_single_record(self):
        records = [{
            "ndc_description": "METFORMIN HCL 500 MG",
            "pricing_unit": "EA",
            "nadac_per_unit": "0.02123",
            "effective_date": "2024-12-04",
            "classification_for_rate_setting": "G",
            "ndc": "00228200310",
            "package_size": "100",
        }]
        result = _format_cost_display(records, "Metformin")
        assert result != {}
        assert result["nadac_per_unit"] == pytest.approx(0.02123)
        assert result["ndc"] == "00228200310"
        assert "METFORMIN" in result["ndc_description"]
        assert result["forms_count"] == 1
        assert "$" in result["display_text"]

    def test_multiple_formulations(self):
        records = [
            {
                "ndc_description": "METFORMIN HCL 500 MG",
                "pricing_unit": "EA",
                "nadac_per_unit": "0.02",
                "effective_date": "2024-12-04",
                "classification_for_rate_setting": "G",
                "ndc": "001", "package_size": "100",
            },
            {
                "ndc_description": "METFORMIN HCL 1000 MG",
                "pricing_unit": "EA",
                "nadac_per_unit": "0.05",
                "effective_date": "2024-12-04",
                "classification_for_rate_setting": "G",
                "ndc": "002", "package_size": "100",
            },
        ]
        result = _format_cost_display(records, "Metformin")
        assert result["forms_count"] == 2
        # Cheapest first
        assert result["cheapest_per_unit"] == pytest.approx(0.02)

    def test_invalid_price_skipped(self):
        records = [
            {
                "ndc_description": "DRUG X",
                "pricing_unit": "EA",
                "nadac_per_unit": "not-a-number",
                "effective_date": "2024-12-04",
                "classification_for_rate_setting": "G",
                "ndc": "001", "package_size": "100",
            },
        ]
        assert _format_cost_display(records, "DrugX") == {}


# ═══════════════════════════════════════════
# OpenFDA HELPERS
# ═══════════════════════════════════════════

class TestOpenFDAHelpers:
    def test_clean_text_string(self):
        assert _clean_text("Simple text") == "Simple text"

    def test_clean_text_list(self):
        result = _clean_text(["<b>Bold</b>", "Normal"])
        assert "<b>" not in result
        assert "Bold" in result
        assert "Normal" in result

    def test_clean_text_none(self):
        assert _clean_text(None) == ""

    def test_clean_text_truncation(self):
        long_text = "x" * 5000
        result = _clean_text(long_text, max_len=100)
        assert len(result) <= 104  # 100 + "..."

    def test_extract_severity_contraindicated(self):
        # "contraindicated" is its own category in the function
        assert _extract_severity("Contraindicated, fatal risk") == "contraindicated"

    def test_extract_severity_major(self):
        assert _extract_severity("Serious hepatotoxicity reported") == "major"

    def test_extract_severity_moderate(self):
        text = "Use caution when combining these"
        assert _extract_severity(text) == "moderate"

    def test_extract_severity_minor(self):
        assert _extract_severity("No known clinical concern") == "minor"


# ═══════════════════════════════════════════
# ORM MODEL SERIALIZATION (.to_dict)
# ═══════════════════════════════════════════

class TestModelSerialization:
    """Verify that to_dict() returns all expected fields for each model."""

    def test_source_to_dict(self, client):
        src = Source.query.get(1)
        d = src.to_dict()
        assert d["authority"] == "FDA"
        assert d["publication_year"] == 2024
        assert d["effective_date"] == "2024-08-21"
        assert "url" in d

    def test_drug_to_dict_summary(self, client):
        drug = Drug.query.get(1)
        d = drug.to_dict(include_details=False)
        assert d["generic_name"] == "Metformin"
        assert "Glucophage" in d["brand_names"]
        assert d["source"]["authority"] == "FDA"
        # Summary should NOT include sub-lists
        assert "indications" not in d
        assert "safety_warnings" not in d

    def test_drug_to_dict_details(self, client):
        drug = Drug.query.get(1)
        d = drug.to_dict(include_details=True)
        assert len(d["indications"]) >= 1
        assert len(d["safety_warnings"]) >= 1
        assert len(d["pricing"]) >= 1
        assert len(d["interactions"]) >= 1

    def test_safety_warning_to_dict_faers(self, client):
        """SafetyWarning.to_dict should deserialize FAERS JSON fields."""
        sw = SafetyWarning.query.filter_by(drug_id=1).first()
        d = sw.to_dict()
        assert d["adverse_event_count"] == 428835
        assert d["adverse_event_serious_count"] == 285519
        assert isinstance(d["top_adverse_reactions"], list)
        assert len(d["top_adverse_reactions"]) >= 5
        assert d["top_adverse_reactions"][0]["reaction"] == "NAUSEA"

    def test_safety_warning_no_faers(self, client):
        """Lisinopril has no FAERS data — fields should be None / empty."""
        sw = SafetyWarning.query.filter_by(drug_id=2).first()
        d = sw.to_dict()
        assert d["adverse_event_count"] is None
        assert d["adverse_event_serious_count"] is None
        assert d["top_adverse_reactions"] == []

    def test_pricing_to_dict_nadac(self, client):
        p = Pricing.query.filter_by(drug_id=1).first()
        d = p.to_dict()
        assert d["nadac_per_unit"] == pytest.approx(0.02123)
        assert d["nadac_ndc"] == "00228200310"
        assert d["nadac_effective_date"] == "2024-12-04"
        assert d["nadac_package_description"] == "METFORMIN HCL 500 MG TABLET"
        assert d["pricing_source"] == "NADAC"

    def test_pricing_to_dict_estimate(self, client):
        p = Pricing.query.filter_by(drug_id=2).first()
        d = p.to_dict()
        assert d["pricing_source"] == "estimate"
        assert d["nadac_per_unit"] is None
        assert d["nadac_ndc"] is None

    def test_interaction_to_dict(self, client):
        ix = DrugInteraction.query.filter_by(drug_id=1).first()
        d = ix.to_dict()
        assert "interacting_drug" in d
        assert "severity" in d
        assert "description" in d
        assert d["source"] is not None
