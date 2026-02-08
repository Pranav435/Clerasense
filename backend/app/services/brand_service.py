"""
Brand product service – fetches and stores per-brand / per-manufacturer
product data for a generic drug from OpenFDA and NADAC.

Each "brand product" is a distinct labelled formulation:
  e.g. "Lipitor 10 mg film-coated tablet by Pfizer" is one brand product
       while "Atorvastatin Calcium 10 mg tablet by Teva" is another.

Data sources:
  - OpenFDA Drug Label API → brand names, manufacturer, dosage form,
    route, active/inactive ingredients, product type, NDC
  - CMS NADAC → per-NDC pricing
"""

import concurrent.futures
import json
import logging
import re
import time
from datetime import datetime
from typing import Optional

import requests

from app.database import db
from app.models.models import Drug, BrandProduct

logger = logging.getLogger("clerasense.brands")

LABEL_URL = "https://api.fda.gov/drug/label.json"
NADAC_URL = "https://data.medicaid.gov/api/1/datastore/query/dfa2ab14-06c2-457a-9e36-5cb6d80f8d93/0"
SEARCH_DELAY = 0.3  # Short delay for on-demand


# ── OpenFDA helpers ──────────────────────────────────────────────────

def _fda_search_labels(generic_name: str, limit: int = 50) -> list[dict]:
    """Fetch up to *limit* FDA labels for a generic drug name."""
    try:
        time.sleep(SEARCH_DELAY)
        resp = requests.get(LABEL_URL, params={
            "search": f'openfda.generic_name:"{generic_name}"',
            "limit": min(limit, 99),
        }, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("results", [])
    except Exception as exc:
        logger.warning("Brand FDA search failed for '%s': %s", generic_name, exc)
    return []


def _extract_brand_entries(labels: list[dict], generic_name: str) -> list[dict]:
    """
    Parse FDA label results into a list of brand-product dicts.
    Each unique (brand_name, manufacturer, dosage_form, route) becomes a row.
    """
    seen = set()
    entries: list[dict] = []
    name_lower = generic_name.lower()

    for label in labels:
        openfda = label.get("openfda", {})
        brand_names = openfda.get("brand_name", [])
        manufacturers = openfda.get("manufacturer_name", [])
        routes = openfda.get("route", [])
        dosage_forms = openfda.get("dosage_form", [])
        product_types = openfda.get("product_type", [])
        ndcs = openfda.get("product_ndc", [])

        # Active ingredients from SPL fields
        active_ingredients_raw = openfda.get("substance_name", [])
        # Inactive ingredients from label text (first 500 chars)
        inactive_raw = ""
        if label.get("inactive_ingredient"):
            raw_list = label["inactive_ingredient"]
            inactive_raw = (raw_list[0] if isinstance(raw_list, list) else str(raw_list))[:500]
            inactive_raw = re.sub(r"<[^>]+>", " ", inactive_raw)
            inactive_raw = re.sub(r"\s+", " ", inactive_raw).strip()

        # Determine if this is a combination product
        gen_names = [g.lower() for g in openfda.get("generic_name", [])]
        is_combo = any(
            " and " in gn or "/" in gn or "," in gn
            for gn in gen_names
        )

        # Extract strength from dosage_and_administration or description
        strength = ""
        desc = openfda.get("package_ndc", [])
        # Try to parse from label description field
        if label.get("description"):
            desc_text = label["description"]
            if isinstance(desc_text, list):
                desc_text = desc_text[0]
            # Look for patterns like "10 mg", "500 mg/5 mL"
            m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|mL|IU)(?:/\d+\s*(?:mg|mcg|g|mL|IU))?)", str(desc_text))
            if m:
                strength = m.group(1)

        manufacturer = manufacturers[0].strip().title() if manufacturers else ""
        brand = brand_names[0].strip().title() if brand_names else generic_name.title()
        route = ", ".join(r.title() for r in routes) if routes else ""
        dosage_form = ", ".join(d.title() for d in dosage_forms) if dosage_forms else ""
        product_type = product_types[0].upper() if product_types else ""
        ndc = ndcs[0] if ndcs else ""

        # Build FDA drug page URL for this specific label
        spl_id = openfda.get("spl_id", [""])[0]
        if spl_id:
            source_url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl_id}"
        else:
            import urllib.parse
            source_url = (
                "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query="
                + urllib.parse.quote_plus(brand)
            )

        # Dedup key
        key = (brand.lower(), manufacturer.lower(), dosage_form.lower(), route.lower())
        if key in seen:
            continue
        seen.add(key)

        # Build full prescribable medicine name
        parts = [brand]
        if strength:
            parts.append(strength)
        if dosage_form:
            parts.append(dosage_form)
        medicine_name = " ".join(parts)

        entries.append({
            "brand_name": brand,
            "medicine_name": medicine_name,
            "manufacturer": manufacturer,
            "ndc": ndc,
            "dosage_form": dosage_form,
            "strength": strength,
            "route": route,
            "is_combination": is_combo,
            "active_ingredients": json.dumps(active_ingredients_raw),
            "inactive_ingredients_summary": inactive_raw[:500] if inactive_raw else "",
            "product_type": product_type,
            "source_url": source_url,
            "source_authority": "FDA",
        })

    return entries


# ── NADAC pricing for individual NDCs ────────────────────────────────

def _nadac_pricing_by_name(generic_name: str) -> dict[str, dict]:
    """
    Fetch NADAC prices for a drug name.
    Returns {ndc_description_upper: pricing_dict}.
    """
    pricing: dict[str, dict] = {}
    try:
        time.sleep(SEARCH_DELAY)
        resp = requests.get(NADAC_URL, params={
            "limit": 100,
            "offset": 0,
            "conditions[0][property]": "ndc_description",
            "conditions[0][value]": f"%{generic_name.upper()}%",
            "conditions[0][operator]": "LIKE",
            "sort": "effective_date",
            "sort_order": "desc",
        }, headers={"Accept": "application/json"}, timeout=30)
        if resp.status_code == 200:
            data = resp.json().get("results", [])
            for rec in data:
                desc = (rec.get("ndc_description") or "").upper()
                if desc not in pricing:
                    try:
                        unit_price = float(rec.get("nadac_per_unit", 0))
                    except (ValueError, TypeError):
                        continue
                    if unit_price <= 0:
                        continue
                    pricing[desc] = {
                        "nadac_per_unit": unit_price,
                        "nadac_unit": rec.get("pricing_unit", "EA"),
                        "nadac_effective_date": rec.get("effective_date", ""),
                        "approximate_cost": f"${unit_price:.4f}/{rec.get('pricing_unit', 'EA')}",
                    }
    except Exception as exc:
        logger.warning("NADAC brand pricing fetch failed: %s", exc)
    return pricing


def _match_pricing_to_brands(entries: list[dict], nadac: dict[str, dict], generic_name: str) -> None:
    """Enrich brand entries with NADAC pricing data where NDC descriptions match."""
    gen_upper = generic_name.upper()
    for entry in entries:
        brand_upper = entry["brand_name"].upper()
        mfr_upper = (entry.get("manufacturer") or "").upper()
        # Try to match by brand name or manufacturer in NADAC description
        for desc, price_info in nadac.items():
            if brand_upper in desc or (mfr_upper and mfr_upper[:15] in desc) or desc.startswith(gen_upper):
                # Additional match: dosage form
                form_upper = (entry.get("dosage_form") or "").upper()
                if form_upper and any(f in desc for f in form_upper.split(",")):
                    entry.update(price_info)
                    break
                elif not entry.get("nadac_per_unit"):
                    entry.update(price_info)
        # If still no match but generic matches, assign cheapest generic NADAC
        if not entry.get("nadac_per_unit"):
            for desc, price_info in nadac.items():
                if desc.startswith(gen_upper):
                    entry.update(price_info)
                    break


# ── Public API: fetch & store brand products  ────────────────────────

def fetch_and_store_brands(drug: Drug) -> list[dict]:
    """
    Fetch brand-level product data from OpenFDA + NADAC and store in DB.
    Replaces any existing brand_products rows for this drug.
    Returns the list of brand dicts.
    """
    generic_name = drug.generic_name

    # Fetch OpenFDA labels and NADAC pricing in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        labels_future = pool.submit(_fda_search_labels, generic_name)
        nadac_future = pool.submit(_nadac_pricing_by_name, generic_name)
        labels = labels_future.result()
        nadac = nadac_future.result()

    # Parse labels into brand entries
    entries = _extract_brand_entries(labels, generic_name)

    # Enrich with NADAC pricing
    if nadac:
        _match_pricing_to_brands(entries, nadac, generic_name)

    # If OpenFDA returned nothing, generate minimal entries from existing brand_names
    if not entries and drug.brand_names:
        for bn in drug.brand_names:
            entries.append({
                "brand_name": bn,
                "medicine_name": bn,
                "manufacturer": "",
                "ndc": "",
                "dosage_form": "",
                "strength": "",
                "route": "",
                "is_combination": False,
                "active_ingredients": json.dumps([generic_name.title()]),
                "inactive_ingredients_summary": "",
                "product_type": "",
                "source_url": "",
                "source_authority": "FDA",
            })

    if not entries:
        return []

    # Delete old US rows and insert fresh ones
    BrandProduct.query.filter_by(drug_id=drug.id, market_country="US").delete()

    for e in entries:
        bp = BrandProduct(
            drug_id=drug.id,
            brand_name=e["brand_name"],
            medicine_name=e.get("medicine_name", e["brand_name"]),
            manufacturer=e.get("manufacturer", ""),
            ndc=e.get("ndc", ""),
            dosage_form=e.get("dosage_form", ""),
            strength=e.get("strength", ""),
            route=e.get("route", ""),
            is_combination=e.get("is_combination", False),
            active_ingredients=e.get("active_ingredients", "[]"),
            inactive_ingredients_summary=e.get("inactive_ingredients_summary", ""),
            product_type=e.get("product_type", ""),
            nadac_per_unit=e.get("nadac_per_unit"),
            nadac_unit=e.get("nadac_unit", ""),
            nadac_effective_date=e.get("nadac_effective_date", ""),
            approximate_cost=e.get("approximate_cost", ""),
            source_url=e.get("source_url", ""),
            source_authority=e.get("source_authority", "FDA"),
            market_country="US",
        )
        db.session.add(bp)

    db.session.commit()
    logger.info("Stored %d brand products for '%s'", len(entries), generic_name)

    return [bp_to_dict(e, drug.id) for e in entries]


def bp_to_dict(entry: dict, drug_id: int) -> dict:
    """Convert a raw entry dict to the same shape as BrandProduct.to_dict()."""
    active = []
    raw = entry.get("active_ingredients", "[]")
    try:
        active = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        active = [raw] if raw else []
    return {
        "drug_id": drug_id,
        "brand_name": entry.get("brand_name", ""),
        "medicine_name": entry.get("medicine_name", entry.get("brand_name", "")),
        "manufacturer": entry.get("manufacturer", ""),
        "ndc": entry.get("ndc", ""),
        "dosage_form": entry.get("dosage_form", ""),
        "strength": entry.get("strength", ""),
        "route": entry.get("route", ""),
        "is_combination": entry.get("is_combination", False),
        "active_ingredients": active,
        "inactive_ingredients_summary": entry.get("inactive_ingredients_summary", ""),
        "product_type": entry.get("product_type", ""),
        "nadac_per_unit": entry.get("nadac_per_unit"),
        "nadac_unit": entry.get("nadac_unit", ""),
        "nadac_effective_date": entry.get("nadac_effective_date", ""),
        "approximate_cost": entry.get("approximate_cost", ""),
        "source_url": entry.get("source_url", ""),
        "source_authority": entry.get("source_authority", "FDA"),
        "market_country": entry.get("market_country", "US"),
    }


def get_brands_for_drug(drug: Drug) -> list[dict]:
    """
    Return US FDA brand products for a drug. If none in DB, fetch on-demand.
    """
    existing = BrandProduct.query.filter_by(drug_id=drug.id, market_country="US").all()
    if existing:
        return [bp.to_dict() for bp in existing]

    # On-demand fetch
    return fetch_and_store_brands(drug)
