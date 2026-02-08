"""Script to surgically replace the broken scraper section in market_brand_service.py."""
import pathlib

SRC = pathlib.Path("app/services/market_brand_service.py")
text = SRC.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
print(f"Original file: {len(lines)} lines")

# Find the section to cut: from the "Real-time web search" header
# to just before the "Helper to build a brand entry dict" header.
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if "Real-time web search" in line and start_idx is None:
        # Go back one line to include the ═══ bar above
        start_idx = i - 1 if i > 0 and "═══" in lines[i-1] else i
    if "Helper to build a brand entry dict" in line:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    print(f"ERROR: Could not find markers. start={start_idx}, end={end_idx}")
    exit(1)

# We also need to go back to include the blank line before the section
while start_idx > 0 and lines[start_idx - 1].strip() == "":
    start_idx -= 1

print(f"Cutting lines {start_idx+1} to {end_idx} (0-indexed: {start_idx}:{end_idx})")
print(f"  First cut line: {lines[start_idx][:60]!r}")
print(f"  Last cut line:  {lines[end_idx-1][:60]!r}")

# New code to insert
NEW_CODE = r'''

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


'''

# Assemble new file
before = lines[:start_idx]
after = lines[end_idx:]  # includes the "Helper to build" header line onward
new_text = "".join(before) + NEW_CODE + "".join(after)

SRC.write_text(new_text, encoding="utf-8")
new_lines = new_text.splitlines()
print(f"New file: {len(new_lines)} lines")
print("Done!")
