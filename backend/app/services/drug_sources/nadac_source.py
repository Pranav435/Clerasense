"""
CMS NADAC (National Average Drug Acquisition Cost) pricing source.
Source: https://data.medicaid.gov/dataset/dfa2ab14-06c2-457a-9e36-5cb6d80f8d93
Authority: Centers for Medicare & Medicaid Services (CMS)
Free, no API key required. Powered by Socrata Open Data API.

NADAC provides the national average drug acquisition cost that retail
community pharmacies pay to acquire prescription and OTC drugs covered
under Medicaid. Updated weekly.
"""

import logging
import time
from datetime import datetime
from typing import Optional

import requests

from app.services.drug_sources.base_source import DrugDataSource, NormalizedDrugData

logger = logging.getLogger("clerasense.sources.nadac")

# Medicaid.gov DKAN datastore API for NADAC
NADAC_URL = "https://data.medicaid.gov/api/1/datastore/query/dfa2ab14-06c2-457a-9e36-5cb6d80f8d93/0"
SEARCH_DELAY = 0.5


def _format_cost_display(records: list[dict], generic_name: str) -> dict:
    """
    Build rich pricing information from NADAC records.
    Returns dict with display text, unit price, NDC, package, effective date.
    """
    if not records:
        return {}

    # Separate by pricing_unit and pick the most recent per form
    by_form: dict[str, dict] = {}
    for rec in records:
        ndc_desc = rec.get("ndc_description", "")
        pricing_unit = rec.get("pricing_unit", "")
        nadac_per_unit = rec.get("nadac_per_unit")
        eff_date = rec.get("effective_date", "")
        classification = rec.get("classification_for_rate_setting", "")
        ndc = rec.get("ndc", "")
        pkg_size = rec.get("package_size", "")

        if not nadac_per_unit:
            continue

        try:
            unit_price = float(nadac_per_unit)
        except (ValueError, TypeError):
            continue

        # Build a form key from description
        form_key = ndc_desc.lower().strip()[:80] if ndc_desc else f"form_{pricing_unit}"

        existing = by_form.get(form_key)
        if not existing or eff_date > existing.get("effective_date", ""):
            by_form[form_key] = {
                "ndc_description": ndc_desc,
                "nadac_per_unit": unit_price,
                "pricing_unit": pricing_unit,
                "effective_date": eff_date[:10] if eff_date else "",
                "classification": classification,
                "ndc": ndc,
                "package_size": pkg_size,
            }

    if not by_form:
        return {}

    # Pick the most common / cheapest oral tablet form if available,
    # otherwise just take all unique forms
    forms = sorted(by_form.values(), key=lambda x: x["nadac_per_unit"])

    # Build display text
    lines = []
    for form in forms[:5]:  # Cap at 5 formulations
        price = form["nadac_per_unit"]
        unit = form["pricing_unit"]
        desc = form["ndc_description"]
        eff = form["effective_date"]

        # Estimate monthly cost (30 units for daily medications)
        if unit.upper() in ("EA", "EACH", "TAB", "CAP"):
            monthly_low = price * 30
            monthly_high = price * 90  # 3x for higher dosing
            line = f"${price:.4f}/{unit} → ~${monthly_low:.2f}–${monthly_high:.2f}/month"
        elif unit.upper() in ("ML", "GM", "GR"):
            line = f"${price:.4f}/{unit}"
        else:
            line = f"${price:.4f}/{unit}"

        line += f" ({desc})" if desc else ""
        lines.append(line)

    # Build summary
    cheapest = forms[0]["nadac_per_unit"]
    most_expensive = forms[-1]["nadac_per_unit"] if len(forms) > 1 else cheapest

    # Use the most recent primary record
    primary = forms[0]

    return {
        "display_text": "; ".join(lines[:3]),
        "nadac_per_unit": primary["nadac_per_unit"],
        "ndc": primary["ndc"],
        "ndc_description": primary["ndc_description"],
        "package_size": primary["package_size"],
        "pricing_unit": primary["pricing_unit"],
        "effective_date": primary["effective_date"],
        "classification": primary["classification"],
        "cheapest_per_unit": cheapest,
        "forms_count": len(forms),
    }


class NADACSource(DrugDataSource):
    """Fetch real drug pricing data from CMS NADAC (Medicaid.gov)."""

    @property
    def source_name(self) -> str:
        return "CMS NADAC Pricing"

    @property
    def source_authority(self) -> str:
        return "CMS"

    def _api_get(self, drug_name: str, limit: int = 50) -> Optional[list]:
        """Rate-limited GET to NADAC DKAN datastore API, searching by drug name."""
        try:
            time.sleep(SEARCH_DELAY)
            params = {
                "limit": limit,
                "offset": 0,
                "conditions[0][property]": "ndc_description",
                "conditions[0][value]": f"%{drug_name.upper()}%",
                "conditions[0][operator]": "LIKE",
                "sort": "effective_date",
                "sort_order": "desc",
            }
            headers = {"Accept": "application/json"}
            resp = requests.get(NADAC_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
            logger.warning("NADAC API returned %s: %s", resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as exc:
            logger.error("NADAC request failed: %s", exc)
            return None

    def search_drugs(self, query: str, limit: int = 10) -> list[str]:
        """Search NADAC for drugs matching a name."""
        data = self._api_get(query, limit=min(limit, 50))
        if not data:
            return []

        names = set()
        for rec in data:
            desc = rec.get("ndc_description", "")
            if desc:
                # Extract drug name from description (before strength info)
                parts = desc.split()
                if parts:
                    name = parts[0].strip().title()
                    names.add(name)
        return list(names)[:limit]

    def fetch_drug_data(self, generic_name: str) -> Optional[NormalizedDrugData]:
        """
        Fetch NADAC pricing data for a drug.
        Returns NormalizedDrugData with pricing fields populated.
        Prioritises single-ingredient matches over combination products.
        """
        data = self._api_get(generic_name, limit=50)
        if not data:
            return None

        # Separate single-ingredient matches from combo products
        drug_upper = generic_name.upper().strip()
        single_ingredient = []
        combo = []
        for rec in data:
            desc = (rec.get("ndc_description") or "").upper()
            # Single-ingredient: description starts with drug name and no hyphen before it
            # e.g. "METFORMIN HCL 500 MG" vs "GLYBURIDE-METFORMIN 5-500 MG"
            if desc.startswith(drug_upper):
                single_ingredient.append(rec)
            elif f"{drug_upper} " in desc and "-" not in desc.split(drug_upper)[0]:
                single_ingredient.append(rec)
            else:
                combo.append(rec)

        # Prefer single-ingredient; fall back to combos
        preferred = single_ingredient if single_ingredient else combo
        pricing_info = _format_cost_display(preferred, generic_name)
        if not pricing_info:
            return None

        display = pricing_info["display_text"]
        eff_date = pricing_info.get("effective_date", "")

        # Build source year from effective date
        try:
            source_year = int(eff_date[:4]) if eff_date else datetime.now().year
        except (ValueError, IndexError):
            source_year = datetime.now().year

        # Determine generic availability from classification
        classification = pricing_info.get("classification", "").upper()
        generic_available = "G" in classification  # G = Generic in NADAC

        return NormalizedDrugData(
            generic_name=generic_name.title(),
            approximate_cost=display,
            generic_available=generic_available,
            nadac_per_unit=pricing_info.get("nadac_per_unit"),
            nadac_ndc=pricing_info.get("ndc", ""),
            nadac_effective_date=eff_date,
            nadac_package_description=pricing_info.get("ndc_description", ""),
            source_authority="CMS",
            source_document_title=f"NADAC Weekly Price – {generic_name.title()}",
            source_url=f"https://data.medicaid.gov/dataset/dfa2ab14-06c2-457a-9e36-5cb6d80f8d93",
            source_year=source_year,
            data_retrieved_at=datetime.utcnow().isoformat(),
        )

    def fetch_interactions(self, generic_name: str) -> list[dict]:
        """NADAC is a pricing-only source — no interaction data."""
        return []

    def fetch_pricing_only(self, generic_name: str) -> Optional[dict]:
        """
        Lightweight pricing fetch — returns raw pricing dict without
        building a full NormalizedDrugData. Used by ingestion service
        to enrich pricing data without a full source fetch.
        """
        data = self._api_get(generic_name, limit=50)
        if not data:
            return None

        # Prefer single-ingredient matches
        drug_upper = generic_name.upper().strip()
        single_ingredient = []
        combo = []
        for rec in data:
            desc = (rec.get("ndc_description") or "").upper()
            if desc.startswith(drug_upper):
                single_ingredient.append(rec)
            elif f"{drug_upper} " in desc and "-" not in desc.split(drug_upper)[0]:
                single_ingredient.append(rec)
            else:
                combo.append(rec)

        preferred = single_ingredient if single_ingredient else combo
        pricing_info = _format_cost_display(preferred, generic_name)
        if not pricing_info:
            return None

        pricing_info["source_authority"] = "CMS"
        pricing_info["source_url"] = "https://data.medicaid.gov/dataset/dfa2ab14-06c2-457a-9e36-5cb6d80f8d93"
        return pricing_info
