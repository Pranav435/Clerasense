"""
Market-specific brand discovery service.

Fetches brand names for a drug available in a specific country/market
using **verified structured data sources**:

  1. **India** – Indian Medicine Dataset (GitHub, 254K+ real medicines with
     brand name, manufacturer, price, composition) – fetched fresh on demand.
  2. **International** – NIH RxNorm REST API (structured drug concept data
     with brand names, dosage forms, strengths).
  3. **Canada** – Health Canada Drug Product Database (DPD) REST API.
  4. **Fallback** – Curated local JSON catalogue, then FDA FAERS reports.
  5. **US** – OpenFDA Drug Label API + CMS NADAC (via brand_service.py).
"""

import json
import logging
import os
import re
import time
import threading
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus

import requests

from app.database import db
from app.models.models import Drug, BrandProduct

logger = logging.getLogger("clerasense.market_brands")

# ── API endpoints ────────────────────────────────────────────────────
FAERS_URL = "https://api.fda.gov/drug/event.json"
HC_DPD_BASE = "https://health-products.canada.ca/api/drug"
SEARCH_DELAY = 0.3          # polite rate-limit pause

# ── US ↔ INN name mapping (common differences) ──────────────────────
US_TO_INN = {
    "acetaminophen": "paracetamol",
    "albuterol": "salbutamol",
    "epinephrine": "adrenaline",
    "meperidine": "pethidine",
    "norepinephrine": "noradrenaline",
    "cyclosporine": "ciclosporin",
    "furosemide": "frusemide",
    "phenytoin": "phenytoin",       # same INN
    "atorvastatin": "atorvastatin", # same INN
}
INN_TO_US = {v: k for k, v in US_TO_INN.items() if k != v}

COUNTRY_NAMES = {
    "US": "United States", "IN": "India", "CA": "Canada",
    "GB": "United Kingdom", "AU": "Australia", "DE": "Germany",
    "FR": "France", "JP": "Japan", "BR": "Brazil", "MX": "Mexico",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
    "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka",
    "NP": "Nepal", "CN": "China", "KR": "South Korea",
    "IT": "Italy", "ES": "Spain", "NL": "Netherlands",
    "SE": "Sweden", "CH": "Switzerland", "SG": "Singapore",
    "MY": "Malaysia", "PH": "Philippines", "ID": "Indonesia",
    "TH": "Thailand", "AE": "UAE", "SA": "Saudi Arabia",
}


# ── Curated data cache ───────────────────────────────────────────────
_CURATED_CACHE: dict[str, dict] = {}  # country_code → full JSON dict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# HTTP session for page fetching (reuses connections)
_HTTP = requests.Session()
_HTTP.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


# ── Helpers ──────────────────────────────────────────────────────────

def get_country_name(code: str) -> str:
    """Return a human-readable country name for a 2-letter ISO code."""
    return COUNTRY_NAMES.get(code.upper(), code.upper())


def _get_search_names(generic_name: str) -> list[str]:
    """Return all known names for a drug (US USAN + international INN)."""
    names = {generic_name.lower()}
    lower = generic_name.lower()
    if lower in US_TO_INN:
        names.add(US_TO_INN[lower])
    if lower in INN_TO_US:
        names.add(INN_TO_US[lower])
    return list(names)


def _extract_strength(name: str) -> str:
    """Try to extract a strength like '650 mg' from a product name string."""
    m = re.search(
        r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|mg/ml|%)\b)", name, re.IGNORECASE
    )
    return m.group(1).strip() if m else ""


def _safe_fetch(url: str, timeout: int = 15) -> str | None:
    """Fetch a URL and return UTF-8 text, or None on failure."""
    try:
        time.sleep(SEARCH_DELAY)
        resp = _HTTP.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
    except Exception as exc:
        logger.debug("Fetch failed %s: %s", url[:80], exc)
    return None


# ═══════════════════════════════════════════════════════════════════════
# Indian Medicine Dataset  (PRIMARY source for India)
# ═══════════════════════════════════════════════════════════════════════

_INDIAN_DATASET_URL = (
    "https://raw.githubusercontent.com/junioralive/"
    "Indian-Medicine-Dataset/main/DATA/indian_medicine_data.json"
)

# Thread-safe cache: stores (timestamp, data_list)
_indian_cache_lock = threading.Lock()
_indian_cache: dict = {"ts": 0.0, "data": None}
_INDIAN_CACHE_TTL = 3600  # 1 hour — re-fetch for freshness


def _fetch_indian_dataset() -> list[dict]:
    """
    Fetch the full Indian Medicine Dataset from GitHub.

    Returns the cached copy if fetched within the last hour, otherwise
    downloads the latest version (user requirement: always up-to-date).
    """
    now = time.time()
    with _indian_cache_lock:
        if _indian_cache["data"] is not None and (now - _indian_cache["ts"]) < _INDIAN_CACHE_TTL:
            return _indian_cache["data"]

    logger.info("Downloading Indian Medicine Dataset from GitHub …")
    try:
        resp = requests.get(_INDIAN_DATASET_URL, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            logger.warning("Indian dataset: unexpected format (not a list)")
            return _indian_cache.get("data") or []
        with _indian_cache_lock:
            _indian_cache["data"] = data
            _indian_cache["ts"] = time.time()
        logger.info("Indian dataset loaded: %d records", len(data))
        return data
    except Exception as exc:
        logger.warning("Failed to fetch Indian dataset: %s", exc)
        # Return stale cache if available
        with _indian_cache_lock:
            return _indian_cache.get("data") or []


def _indian_dataset_discover_brands(generic_name: str) -> list[dict]:
    """
    Search the Indian Medicine Dataset (254K+ real medicines) for brands
    containing *generic_name* as an active ingredient.

    Matches against the ``short_composition1`` field which contains the
    primary active ingredient, e.g. ``"Paracetamol (500mg)"``.
    """
    dataset = _fetch_indian_dataset()
    if not dataset:
        return []

    search_names = _get_search_names(generic_name)
    search_lower = [n.lower() for n in search_names]

    entries: list[dict] = []
    seen: set[str] = set()

    for record in dataset:
        comp1 = (record.get("short_composition1") or "").lower()
        comp2 = (record.get("short_composition2") or "").lower()

        # Check if any known name variant appears in the composition
        matched = False
        is_combo = False
        for sn in search_lower:
            if sn in comp1:
                matched = True
                break

        if not matched:
            continue

        # If there's a second active ingredient, it's a combination
        if comp2 and comp2.strip():
            is_combo = True

        # Skip discontinued medicines
        if (record.get("Is_discontinued") or "").upper() == "TRUE":
            continue

        brand_name = (record.get("name") or "").strip()
        if not brand_name or len(brand_name) < 2:
            continue

        # Deduplicate by lowercase brand name
        key = brand_name.lower()
        if key in seen:
            continue
        seen.add(key)

        manufacturer = (record.get("manufacturer_name") or "").strip()
        price_raw = str(record.get("price(\u20b9)") or record.get("price") or "").strip()
        pack_size = (record.get("pack_size_label") or "").strip()
        med_type = (record.get("type") or "").strip()

        # Extract strength from composition field, e.g. "Paracetamol (500mg)"
        strength = ""
        for sn in search_lower:
            if sn in comp1:
                m = re.search(
                    re.escape(sn) + r"\s*\(([^)]+)\)", comp1, re.IGNORECASE
                )
                if m:
                    strength = m.group(1).strip()
                break

        # Build dosage form from pack_size_label + type
        dosage_form = ""
        pack_lower = pack_size.lower()
        if "tablet" in pack_lower:
            dosage_form = "Tablet"
        elif "capsule" in pack_lower:
            dosage_form = "Capsule"
        elif "syrup" in pack_lower or "liquid" in pack_lower or "suspension" in pack_lower:
            dosage_form = "Syrup"
        elif "injection" in pack_lower:
            dosage_form = "Injection"
        elif "cream" in pack_lower or "ointment" in pack_lower or "gel" in pack_lower:
            dosage_form = "Topical"
        elif "drop" in pack_lower:
            dosage_form = "Drops"
        elif "inhaler" in pack_lower:
            dosage_form = "Inhaler"
        elif "powder" in pack_lower:
            dosage_form = "Powder"

        # Format approximate cost
        approximate_cost = ""
        if price_raw:
            try:
                price_val = float(price_raw)
                approximate_cost = f"\u20b9{price_val:.2f}"
                if pack_size:
                    approximate_cost += f" ({pack_size})"
            except ValueError:
                approximate_cost = price_raw

        # Build active ingredients list
        active_ingredients = [generic_name.title()]
        if is_combo and comp2:
            # Extract second ingredient name (before the parenthesised strength)
            second = re.sub(r"\s*\(.*?\)", "", comp2).strip().title()
            if second:
                active_ingredients.append(second)

        entries.append(_make_entry(
            brand_name=brand_name,
            manufacturer=manufacturer,
            generic_name=generic_name,
            country_code="IN",
            source_url="https://github.com/junioralive/Indian-Medicine-Dataset",
            source="Indian Medicine Dataset",
            strength=strength,
            dosage_form=dosage_form,
            route="Oral" if dosage_form in ("Tablet", "Capsule", "Syrup") else "",
            price_text=approximate_cost,
            is_combination=is_combo,
            product_type=med_type.title() if med_type else "",
        ))

        # Cap at 50 brands to keep responses manageable
        if len(entries) >= 50:
            break

    logger.info("Indian dataset → %d brands for '%s'", len(entries), generic_name)
    return entries


# ═══════════════════════════════════════════════════════════════════════
# RxNorm API  (structured US brand names — useful internationally)
# ═══════════════════════════════════════════════════════════════════════

_RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"


def _rxnorm_discover_brands(
    generic_name: str,
    country_code: str,
) -> list[dict]:
    """
    Query the NIH RxNorm REST API to discover brand names for a drug.

    Returns structured brand entries extracted from Semantic Branded Drug
    (SBD) concepts, which contain patterns like ``[Glucophage]``.
    """
    search_names = _get_search_names(generic_name)
    brand_names: dict[str, dict] = {}  # lowered brand → {name, dosage_form, strength}

    for name in search_names:
        url = f"{_RXNORM_BASE}/drugs.json?name={quote_plus(name)}"
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as exc:
            logger.debug("RxNorm query '%s': %s", name, exc)
            continue

        groups = data.get("drugGroup", {}).get("conceptGroup", [])
        for group in groups:
            tty = group.get("tty", "")
            # SBD = Semantic Branded Drug, SCD entries have no brand
            if tty not in ("SBD", "BPCK"):
                continue
            for concept in group.get("conceptProperties", []):
                cname = concept.get("name", "")
                # Extract brand from brackets: "metformin 500 MG [Glucophage]"
                m = re.search(r"\[([^\]]+)\]", cname)
                if not m:
                    continue
                brand = m.group(1).strip()
                key = brand.lower()
                if key in brand_names:
                    continue
                # Skip if the brand IS the generic name
                if key in {n.lower() for n in search_names}:
                    continue

                # Parse strength and dosage form from the concept name
                strength = ""
                dosage_form = ""
                sm = re.search(r"(\d+(?:\.\d+)?\s*(?:MG|MCG|ML|MG/ML|UNIT))", cname, re.IGNORECASE)
                if sm:
                    strength = sm.group(1).strip()
                dm = re.search(r"(?:Oral\s+)?(Tablet|Capsule|Solution|Suspension|Injection|Cream|Patch)", cname, re.IGNORECASE)
                if dm:
                    dosage_form = dm.group(1).strip().title()

                brand_names[key] = {
                    "brand": brand,
                    "strength": strength,
                    "dosage_form": dosage_form,
                    "concept_name": cname,
                }

    cc = country_code.upper()
    country_name = get_country_name(cc)
    entries: list[dict] = []

    for info in brand_names.values():
        entries.append(_make_entry(
            brand_name=info["brand"],
            manufacturer="",
            generic_name=generic_name,
            country_code=cc,
            source_url="https://rxnav.nlm.nih.gov/",
            source=f"NIH RxNorm ({country_name})",
            strength=info["strength"],
            dosage_form=info["dosage_form"],
        ))

    logger.info("RxNorm → %d brands for '%s'", len(entries), generic_name)
    return entries[:30]


# ── Helper to build a brand entry dict ───────────────────────────────

def _make_entry(
    brand_name: str,
    manufacturer: str,
    generic_name: str,
    country_code: str,
    *,
    source_url: str = "",
    source: str = "",
    strength: str = "",
    dosage_form: str = "",
    route: str = "",
    price_text: str = "",
    is_combination: bool = False,
    product_type: str = "",
) -> dict:
    """Build a normalised brand entry dict."""
    # Clean up brand name
    brand_name = brand_name.strip()
    brand_name = re.sub(r"\s+", " ", brand_name)

    # Build medicine_name
    parts = [brand_name]
    if not strength:
        strength = _extract_strength(brand_name)
    if strength and strength not in brand_name:
        parts.append(strength)
    if dosage_form:
        parts.append(dosage_form)
    medicine_name = " ".join(parts)

    # Build approx cost from price text
    approximate_cost = ""
    if price_text:
        price_text = re.sub(r"[^\d₹$.,/a-zA-Z ]", "", price_text).strip()
        if price_text:
            approximate_cost = price_text

    cc = country_code.upper() if country_code else ""
    country_name = get_country_name(cc) if cc else ""

    return {
        "brand_name": brand_name,
        "medicine_name": medicine_name,
        "manufacturer": manufacturer.strip(),
        "ndc": "",
        "dosage_form": dosage_form,
        "strength": strength,
        "route": route,
        "is_combination": is_combination,
        "active_ingredients": json.dumps([generic_name.title()]),
        "inactive_ingredients_summary": "",
        "product_type": product_type,
        "source_url": source_url,
        "source_authority": f"{source}" if source else f"Web ({country_name})",
        "market_country": cc,
        "approximate_cost": approximate_cost,
    }


# ═══════════════════════════════════════════════════════════════════════
# Curated brand catalogues  (enrichment / fallback)
# ═══════════════════════════════════════════════════════════════════════

_COUNTRY_FILE_MAP = {
    "IN": "india_brands.json",
    # Add more: "BR": "brazil_brands.json", etc.
}


def _load_curated_data(country_code: str) -> dict:
    """Load and cache a curated brand catalogue for *country_code*."""
    cc = country_code.upper()
    if cc in _CURATED_CACHE:
        return _CURATED_CACHE[cc]

    fname = _COUNTRY_FILE_MAP.get(cc)
    if not fname:
        _CURATED_CACHE[cc] = {}
        return {}

    fpath = DATA_DIR / fname
    if not fpath.exists():
        logger.warning("Curated brand file not found: %s", fpath)
        _CURATED_CACHE[cc] = {}
        return {}

    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        data.pop("_meta", None)
        _CURATED_CACHE[cc] = data
        logger.info("Loaded curated brands for %s: %d drugs", cc, len(data))
    except Exception as exc:
        logger.warning("Failed to load %s: %s", fpath, exc)
        _CURATED_CACHE[cc] = {}

    return _CURATED_CACHE[cc]


def _curated_discover_brands(
    generic_name: str,
    country_code: str,
) -> list[dict]:
    """Look up brands from a curated JSON catalogue (fallback only)."""
    cc = country_code.upper()
    catalogue = _load_curated_data(cc)
    if not catalogue:
        return []

    search_names = _get_search_names(generic_name)
    brands_raw: list[dict] = []
    for name in search_names:
        if name in catalogue:
            brands_raw = catalogue[name]
            break

    if not brands_raw:
        return []

    country_name = get_country_name(cc)
    entries: list[dict] = []
    seen: set[str] = set()

    for b in brands_raw:
        brand = b.get("brand_name", "").strip()
        if not brand:
            continue
        parts = [brand]
        if b.get("strength"):
            parts.append(b["strength"])
        if b.get("dosage_form"):
            parts.append(b["dosage_form"])
        medicine_name = " ".join(parts)

        key = (brand.lower(), b.get("strength", "").lower())
        if key in seen:
            continue
        seen.add(key)

        entries.append({
            "brand_name": brand,
            "medicine_name": medicine_name,
            "manufacturer": b.get("manufacturer", ""),
            "ndc": "",
            "dosage_form": b.get("dosage_form", ""),
            "strength": b.get("strength", ""),
            "route": b.get("route", ""),
            "is_combination": b.get("is_combination", False),
            "active_ingredients": json.dumps([generic_name.title()]),
            "inactive_ingredients_summary": "",
            "product_type": b.get("product_type", ""),
            "source_url": "",
            "source_authority": f"Verified ({country_name})",
            "market_country": cc,
        })

    return entries


def _enrich_with_curated(
    web_brands: list[dict],
    generic_name: str,
    country_code: str,
) -> list[dict]:
    """
    Merge curated catalogue data INTO web-discovered brands.

    • If a web brand matches a curated entry → fill in missing fields.
    • Curated brands not in the web list → append them (so we never lose
      known-good brands like Dolo 650, Ecosprin, etc.).
    """
    curated = _curated_discover_brands(generic_name, country_code)
    if not curated:
        return web_brands

    # Index web brands by lowered name
    web_idx = {b["brand_name"].lower(): b for b in web_brands}

    for c in curated:
        key = c["brand_name"].lower()
        if key in web_idx:
            # Enrich existing web entry
            wb = web_idx[key]
            if not wb.get("manufacturer") and c.get("manufacturer"):
                wb["manufacturer"] = c["manufacturer"]
            if not wb.get("dosage_form") and c.get("dosage_form"):
                wb["dosage_form"] = c["dosage_form"]
            if not wb.get("strength") and c.get("strength"):
                wb["strength"] = c["strength"]
            if not wb.get("route") and c.get("route"):
                wb["route"] = c["route"]
        else:
            # Append curated brand not found by web search
            web_brands.append(c)

    return web_brands


# ═══════════════════════════════════════════════════════════════════════
# FAERS-based brand discovery  (works for ANY country with reports)
# ═══════════════════════════════════════════════════════════════════════

def _faers_request(search_expr: str, limit: int = 100) -> list[dict]:
    """
    Make a FAERS request with *search_expr* already formatted.

    We build the URL **manually** because the openFDA query syntax uses
    literal ``+AND+`` as Boolean AND, but ``requests.get(params=...)``
    percent-encodes it to ``%2BAND%2B`` which the API rejects / ignores.
    """
    import urllib.parse
    url = (
        f"{FAERS_URL}"
        f"?search={search_expr}"
        f"&limit={min(limit, 100)}"
    )
    try:
        time.sleep(SEARCH_DELAY)
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("results", [])
    except Exception as exc:
        logger.warning("FAERS request failed: %s — %s", url[:120], exc)
    return []


def _is_relevant_drug_entry(drug_entry: dict, search_names_upper: set[str]) -> bool:
    """
    Return True if this drug-in-event entry actually refers to our target
    drug (not a co-medication).  Checks openfda.generic_name AND the
    medicinalproduct field against all known name variants.
    """
    # Check openfda.generic_name
    openfda_names = drug_entry.get("openfda", {}).get("generic_name", [])
    for gn in openfda_names:
        for token in gn.upper().split(" AND "):
            if token.strip() in search_names_upper:
                return True

    # Check medicinalproduct itself (may be a brand that contains the name)
    prod = re.sub(r"[\.\,]+$", "", (drug_entry.get("medicinalproduct") or "").upper().strip())
    for sn in search_names_upper:
        if sn in prod:
            return True

    # Also match by openfda.substance_name
    substances = drug_entry.get("openfda", {}).get("substance_name", [])
    for s in substances:
        if s.upper().strip() in search_names_upper:
            return True

    return False


def _faers_discover_brands(
    generic_name: str,
    country_code: str,
    limit: int = 100,
) -> list[dict]:
    """
    Query FDA FAERS adverse-event reports from *country_code* to discover
    the brand / product names used locally for a given generic drug.
    """
    search_names = _get_search_names(generic_name)
    search_names_upper = {n.upper() for n in search_names}
    raw_products: list[str] = []

    cc = country_code.upper()

    # Strategy 1 – search by openfda.generic_name for each name variant
    for name in search_names:
        search_expr = (
            f'patient.drug.openfda.generic_name:"{name}"'
            f"+AND+occurcountry:{cc}"
        )
        events = _faers_request(search_expr, limit)
        for event in events:
            for d in event.get("patient", {}).get("drug", []):
                if not _is_relevant_drug_entry(d, search_names_upper):
                    continue
                prod = (d.get("medicinalproduct") or "").strip()
                if prod:
                    raw_products.append(prod.upper())

    # Strategy 2 – search by medicinalproduct (catches local-name-only reports)
    if not raw_products:
        for name in search_names:
            search_expr = (
                f'patient.drug.medicinalproduct:"{name}"'
                f"+AND+occurcountry:{cc}"
            )
            events = _faers_request(search_expr, limit)
            for event in events:
                for d in event.get("patient", {}).get("drug", []):
                    if not _is_relevant_drug_entry(d, search_names_upper):
                        continue
                    prod = (d.get("medicinalproduct") or "").strip()
                    if prod:
                        raw_products.append(prod.upper())

    # Strategy 3 – search by substance_name (broader fallback)
    if not raw_products:
        for name in search_names:
            search_expr = (
                f'patient.drug.openfda.substance_name:"{name}"'
                f"+AND+occurcountry:{cc}"
            )
            events = _faers_request(search_expr, limit)
            for event in events:
                for d in event.get("patient", {}).get("drug", []):
                    if not _is_relevant_drug_entry(d, search_names_upper):
                        continue
                    prod = (d.get("medicinalproduct") or "").strip()
                    if prod:
                        raw_products.append(prod.upper())

    if not raw_products:
        return []

    # Count occurrences to surface the most-reported brand names first
    counts = Counter(raw_products)

    # Filter out bare generic names and deduplicate
    entries: list[dict] = []
    seen: set[str] = set()

    for product_name, count in counts.most_common(60):
        # Strip trailing periods / punctuation that FAERS often includes
        stripped = re.sub(r"[\.\,\;\:]+$", "", product_name).strip()
        # Skip if it's just the generic name itself (exact match)
        if stripped in search_names_upper:
            continue
        # Skip very short / noise entries
        cleaned = re.sub(r"[^A-Za-z0-9 ]", "", stripped).strip()
        if len(cleaned) < 2:
            continue
        normalised = stripped.strip().title()
        # Clean up trailing slashes, numbers-only suffixes from FAERS padding
        normalised = re.sub(r"\s*/\d+/$", "", normalised).strip()
        normalised = re.sub(r"\s+", " ", normalised).strip()
        key = normalised.lower()
        if key in seen:
            continue
        seen.add(key)

        strength = _extract_strength(product_name)
        entries.append({
            "brand_name": normalised,
            "medicine_name": normalised,
            "manufacturer": "",
            "ndc": "",
            "dosage_form": "",
            "strength": strength,
            "route": "",
            "is_combination": False,
            "active_ingredients": json.dumps([generic_name.title()]),
            "inactive_ingredients_summary": "",
            "product_type": "",
            "source_url": (
                f"https://api.fda.gov/drug/event.json?search="
                f"patient.drug.medicinalproduct:%22{product_name}%22"
                f"+AND+occurcountry:{cc}"
            ),
            "source_authority": f"FDA FAERS ({cc})",
            "market_country": cc,
            "_report_count": count,
        })

    entries.sort(key=lambda x: -x.get("_report_count", 0))
    return entries[:30]


# ═══════════════════════════════════════════════════════════════════════
# Health Canada DPD  (clean REST API for Canadian market)
# ═══════════════════════════════════════════════════════════════════════

def _health_canada_discover_brands(generic_name: str) -> list[dict]:
    """
    Query Health Canada Drug Product Database for Canadian brands.
    Two-step: find drug codes by active ingredient, then get product info.
    """
    search_names = _get_search_names(generic_name)
    drug_codes: set[int] = set()

    for name in search_names:
        try:
            time.sleep(SEARCH_DELAY)
            resp = requests.get(
                f"{HC_DPD_BASE}/activeingredient/",
                params={"lang": "en", "type": "json", "ingredient": name},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        code = item.get("drug_code")
                        if code:
                            drug_codes.add(int(code))
        except Exception as exc:
            logger.warning("HC ingredient search '%s': %s", name, exc)

    if not drug_codes:
        return []

    entries: list[dict] = []
    seen: set[str] = set()

    for code in list(drug_codes)[:50]:
        try:
            resp = requests.get(
                f"{HC_DPD_BASE}/drugproduct/",
                params={"lang": "en", "type": "json", "id": code},
                timeout=20,
            )
            if resp.status_code != 200:
                continue
            products = resp.json()
            if not isinstance(products, list):
                continue

            for prod in products:
                brand = (prod.get("brand_name") or "").strip().title()
                company = (prod.get("company_name") or "").strip().title()
                din = prod.get("drug_identification_number") or ""

                key = (brand.lower(), company.lower())
                if key in seen or not brand:
                    continue
                seen.add(key)

                # Fetch strength / dosage form from ingredient endpoint
                strength, dosage_form = "", ""
                try:
                    ing_resp = requests.get(
                        f"{HC_DPD_BASE}/activeingredient/",
                        params={"lang": "en", "type": "json", "id": code},
                        timeout=15,
                    )
                    if ing_resp.status_code == 200:
                        ings = ing_resp.json()
                        if isinstance(ings, list) and ings:
                            s = ings[0].get("strength") or ""
                            u = ings[0].get("strength_unit") or ""
                            if s:
                                strength = f"{s} {u}".strip()
                            dosage_form = (ings[0].get("dosage_form") or "").title()
                except Exception:
                    pass

                parts = [brand]
                if strength:
                    parts.append(strength)
                if dosage_form:
                    parts.append(dosage_form)
                medicine_name = " ".join(parts)

                entries.append({
                    "brand_name": brand,
                    "medicine_name": medicine_name,
                    "manufacturer": company,
                    "ndc": din,               # DIN for Canada
                    "dosage_form": dosage_form,
                    "strength": strength,
                    "route": (prod.get("route_of_administration") or "").title(),
                    "is_combination": False,
                    "active_ingredients": json.dumps([generic_name.title()]),
                    "inactive_ingredients_summary": "",
                    "product_type": (prod.get("class_name") or "").upper(),
                    "source_url": f"https://health-products.canada.ca/dpd-bdpp/info?code={code}",
                    "source_authority": "Health Canada",
                    "market_country": "CA",
                })
        except Exception as exc:
            logger.warning("HC product lookup code=%s: %s", code, exc)

    return entries[:30]


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def fetch_market_brands(drug: Drug, country_code: str) -> list[dict]:
    """
    Fetch brand products for *drug* in *country_code* market.
    Stores results in the DB and returns dicts.
    """
    country_code = country_code.upper()

    if country_code == "US":
        from app.services.brand_service import fetch_and_store_brands
        return fetch_and_store_brands(drug)

    # Pick the right fetcher – verified structured data sources
    if country_code == "CA":
        entries = _health_canada_discover_brands(drug.generic_name)
    elif country_code == "IN":
        # Layer 1: Indian Medicine Dataset (254K+ real medicines from GitHub)
        entries = _indian_dataset_discover_brands(drug.generic_name)

        # Layer 2: Enrich with curated catalogue (fills manufacturer / dosage gaps)
        entries = _enrich_with_curated(entries, drug.generic_name, country_code)

        # Layer 3: FAERS (absolute last resort)
        if not entries:
            entries = _faers_discover_brands(drug.generic_name, country_code)
    else:
        # Layer 1: RxNorm structured API (NIH brand name database)
        entries = _rxnorm_discover_brands(drug.generic_name, country_code)

        # Layer 2: Enrich with curated catalogue
        entries = _enrich_with_curated(entries, drug.generic_name, country_code)

        # Layer 3: FAERS adverse-event mining (last resort)
        if not entries:
            entries = _faers_discover_brands(drug.generic_name, country_code)

    if not entries:
        return []

    # Delete stale country-specific rows, insert fresh ones
    BrandProduct.query.filter_by(
        drug_id=drug.id, market_country=country_code
    ).delete()

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
            source_authority=e.get("source_authority", ""),
            market_country=country_code,
        )
        db.session.add(bp)

    db.session.commit()
    logger.info(
        "Stored %d market brands for '%s' in %s",
        len(entries), drug.generic_name, country_code,
    )
    return [_to_dict(e, drug.id) for e in entries]


def get_market_brands_for_drug(drug: Drug, country_code: str) -> list[dict]:
    """
    Return market-specific brands, fetching on-demand if not cached.
    """
    country_code = country_code.upper()

    if country_code == "US":
        from app.services.brand_service import get_brands_for_drug
        return get_brands_for_drug(drug)

    existing = BrandProduct.query.filter_by(
        drug_id=drug.id, market_country=country_code,
    ).all()

    if existing:
        return [bp.to_dict() for bp in existing]

    return fetch_market_brands(drug, country_code)


def _to_dict(entry: dict, drug_id: int) -> dict:
    """Convert a raw entry dict to the shape of BrandProduct.to_dict()."""
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
        "source_authority": entry.get("source_authority", ""),
        "market_country": entry.get("market_country", ""),
    }
