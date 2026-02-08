"""
OpenFDA Drug Label + Adverse Events API adapter.
Sources:
  - Drug Label: https://open.fda.gov/apis/drug/label/
  - Adverse Events (FAERS): https://open.fda.gov/apis/drug/event/
Authority: U.S. Food and Drug Administration (FDA)
Rate limit: 40 requests/minute without API key, 240/min with key.
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional

import requests

from app.services.drug_sources.base_source import DrugDataSource, NormalizedDrugData

logger = logging.getLogger("clerasense.sources.openfda")

LABEL_URL = "https://api.fda.gov/drug/label.json"
EVENT_URL = "https://api.fda.gov/drug/event.json"
SEARCH_DELAY = 1.5  # seconds between requests to respect rate limits


def _clean_text(text_list: list | str | None, max_len: int = 3000) -> str:
    """Extract clean text from OpenFDA array-of-strings fields."""
    if not text_list:
        return ""
    if isinstance(text_list, list):
        joined = " ".join(text_list)
    else:
        joined = str(text_list)
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", joined)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Strip ALL section headers/numbers like "12.1 Mechanism of Action", "8.1 Pregnancy"
    # Matches patterns like "4 CONTRAINDICATIONS", "7.1 Drug Interactions", "12.1 Mechanism Of Action"
    cleaned = re.sub(
        r"\b\d{1,2}(?:\.\d{1,2})?\s+[A-Z][A-Za-z\s,&/\-]{2,50}(?=\s[a-z]|\s[A-Z][a-z])",
        " ", cleaned
    )
    # Also strip standalone section titles in ALL-CAPS (e.g., "CONTRAINDICATIONS", "WARNINGS AND PRECAUTIONS")
    cleaned = re.sub(r"\b[A-Z]{4,}(?:\s+(?:AND|OR|IN|OF|FOR|THE|WITH)\s+[A-Z]{3,})*\b(?=\s)", " ", cleaned)
    # Collapse whitespace again after removals
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Truncate very long texts to keep DB reasonable
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "..."
    return cleaned


def _extract_severity(text: str) -> str:
    """Heuristically assign interaction severity from description text."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["contraindicated", "fatal", "death", "do not use"]):
        return "contraindicated"
    if any(w in text_lower for w in ["serious", "severe", "major", "significant", "avoid"]):
        return "major"
    if any(w in text_lower for w in ["moderate", "caution", "monitor closely"]):
        return "moderate"
    return "minor"


def _estimate_cost(drug_name: str, drug_class: str, route: str, generic_available: bool) -> str:
    """
    Provide a rough cost estimate as fallback when NADAC data is unavailable.
    The primary pricing source is now CMS NADAC. This is only used as a
    last-resort approximation.
    """
    if generic_available:
        if "oral" in route or "tablet" in route:
            return "Estimated $4–$30/month (generic; verify with NADAC/pharmacy)"
        elif "injection" in route or "intravenous" in route:
            return "Estimated $10–$100/dose (generic injection; verify with pharmacy)"
        elif "inhalation" in route:
            return "Estimated $20–$80/month (generic inhaler; verify with pharmacy)"
        else:
            return "Estimated $4–$50/month (generic; verify with pharmacy)"
    else:
        class_lower = drug_class.lower() if drug_class else ""
        if "biologic" in class_lower or "monoclonal" in class_lower:
            return "Estimated $1,000–$5,000/month (brand biologic; verify with pharmacy)"
        elif "injection" in route:
            return "Estimated $50–$500/dose (brand injection; verify with pharmacy)"
        elif "oral" in route:
            return "Estimated $30–$200/month (brand oral; verify with pharmacy)"
        else:
            return "Estimated $30–$300/month (brand; verify with pharmacy)"


def _fetch_adverse_events(generic_name: str, delay_scale: float = 1.0) -> dict:
    """
    Fetch adverse event summary from FDA FAERS (Adverse Event Reporting System).
    Returns total count, serious count, and top reactions.
    """
    result = {
        "total_count": None,
        "serious_count": None,
        "top_reactions": [],
    }
    try:
        # 1. Get total event count
        time.sleep(SEARCH_DELAY * delay_scale)
        search_term = f'patient.drug.openfda.generic_name:"{generic_name}"'
        resp = requests.get(EVENT_URL, params={
            "search": search_term,
            "limit": 1,
        }, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            meta = data.get("meta", {}).get("results", {})
            result["total_count"] = meta.get("total", 0)

        # 2. Get serious event count (count=serious returns term:1=serious, term:2=not serious)
        time.sleep(SEARCH_DELAY * delay_scale)
        resp2 = requests.get(EVENT_URL, params={
            "search": search_term,
            "count": "serious",
        }, timeout=20)
        if resp2.status_code == 200:
            data2 = resp2.json()
            # The count endpoint returns [{term: 1, count: N}] for serious=1
            for item in data2.get("results", []):
                if str(item.get("term")) == "1":
                    result["serious_count"] = item.get("count", 0)
                    break
            # Fallback: if count endpoint didn't work, use meta
            if result["serious_count"] is None:
                meta2 = data2.get("meta", {}).get("results", {})
                result["serious_count"] = meta2.get("total", 0)

        # 3. Get top adverse reactions
        time.sleep(SEARCH_DELAY * delay_scale)
        resp3 = requests.get(EVENT_URL, params={
            "search": search_term,
            "count": "patient.reaction.reactionmeddrapt.exact",
        }, timeout=20)
        if resp3.status_code == 200:
            data3 = resp3.json()
            reactions = data3.get("results", [])[:15]  # Top 15
            result["top_reactions"] = [
                {"reaction": r.get("term", ""), "count": r.get("count", 0)}
                for r in reactions
            ]

    except Exception as exc:
        logger.warning("FAERS adverse event fetch failed for '%s': %s", generic_name, exc)

    return result


def _parse_effective_date(label: dict) -> tuple[str, int]:
    """
    Extract the label effective_time from OpenFDA results.
    Returns (iso_date_string, year).
    """
    eff_time = label.get("effective_time", "")
    if eff_time and len(eff_time) >= 4:
        try:
            year = int(eff_time[:4])
            # Format as YYYY-MM-DD
            if len(eff_time) >= 8:
                date_str = f"{eff_time[:4]}-{eff_time[4:6]}-{eff_time[6:8]}"
            else:
                date_str = f"{eff_time[:4]}-01-01"
            return date_str, year
        except (ValueError, IndexError):
            pass
    return "", datetime.now().year


class OpenFDASource(DrugDataSource):
    """Fetch drug labeling data from the OpenFDA Drug Label API."""

    def __init__(self, delay_scale: float = 1.0):
        self.delay_scale = delay_scale

    @property
    def source_name(self) -> str:
        return "OpenFDA Drug Label API"

    @property
    def source_authority(self) -> str:
        return "FDA"

    def _api_get(self, params: dict, url: str = None) -> Optional[dict]:
        """Make a rate-limited GET request to OpenFDA."""
        try:
            time.sleep(SEARCH_DELAY * self.delay_scale)
            resp = requests.get(url or LABEL_URL, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            logger.warning("OpenFDA returned %s: %s", resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as exc:
            logger.error("OpenFDA request failed: %s", exc)
            return None

    def _pick_best_label(self, results: list[dict], generic_name: str) -> dict:
        """
        Pick the best label from OpenFDA results.
        Strongly prefers single-ingredient products and penalises combos,
        so that drug_class and other fields are specific to the queried drug.
        """
        name_lower = generic_name.lower().strip()

        # Score each result
        scored = []
        for label in results:
            openfda = label.get("openfda", {})
            gen_names = [g.lower() for g in openfda.get("generic_name", [])]
            score = 0

            # --- Ingredient match scoring ---
            for gn in gen_names:
                is_combo = " and " in gn or "/" in gn or "," in gn
                if gn == name_lower:
                    score += 300  # Perfect single-ingredient match
                elif gn == f"{name_lower} hydrochloride" or gn == f"{name_lower} hcl":
                    score += 280  # Salt form exact match
                elif gn.startswith(name_lower) and not is_combo:
                    score += 200  # e.g., "metformin hydrochloride extended-release"
                elif name_lower in gn and not is_combo:
                    score += 100  # Single ingredient containing our drug
                elif name_lower in gn and is_combo:
                    score -= 200  # PENALISE combo products heavily

            # Prefer labels with more clinical fields filled
            for field_name in ["contraindications", "warnings_and_cautions", "drug_interactions",
                          "adverse_reactions", "boxed_warning", "pregnancy",
                          "mechanism_of_action", "clinical_pharmacology"]:
                if label.get(field_name):
                    score += 5

            # Prefer labels with dosage info
            if label.get("dosage_and_administration"):
                score += 5

            # Prefer labels from prescription products (not OTC)
            product_type = openfda.get("product_type", [])
            for pt in product_type:
                if "PRESCRIPTION" in str(pt).upper():
                    score += 30
                elif "OTC" in str(pt).upper():
                    score -= 10

            scored.append((score, label))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else results[0]

    def search_drugs(self, query: str, limit: int = 10) -> list[str]:
        """Search for drugs by generic name."""
        params = {
            "search": f'openfda.generic_name:"{query}"',
            "limit": min(limit, 100),
        }
        data = self._api_get(params)
        if not data or "results" not in data:
            return []

        names = set()
        for result in data["results"]:
            openfda = result.get("openfda", {})
            for name in openfda.get("generic_name", []):
                names.add(name.strip().title())
        return list(names)[:limit]

    def fetch_drug_data(self, generic_name: str) -> Optional[NormalizedDrugData]:
        """Fetch comprehensive drug label data from FDA + adverse event data from FAERS."""
        # Fetch multiple results and pick the best label
        params = {
            "search": f'openfda.generic_name:"{generic_name}"',
            "limit": 10,
        }
        data = self._api_get(params)
        if not data or "results" not in data:
            return None

        label = self._pick_best_label(data["results"], generic_name)
        openfda = label.get("openfda", {})

        # Extract brand names
        brand_names = [b.strip().title() for b in openfda.get("brand_name", [])]

        # Drug class from pharmacologic class — validate it's specific to this drug
        raw_drug_classes = openfda.get("pharm_class_epc", [])
        if not raw_drug_classes:
            raw_drug_classes = openfda.get("pharm_class_moa", [])
        # Filter out combo-product classes (contain "combination", "and", etc.)
        combo_keywords = ["combination", " and ", " with "]
        single_classes = [
            c for c in raw_drug_classes
            if not any(kw in c.lower() for kw in combo_keywords)
        ]
        drug_class = ", ".join(single_classes) if single_classes else ", ".join(raw_drug_classes)

        # Mechanism of action
        mechanism = _clean_text(label.get("mechanism_of_action"))
        if not mechanism:
            mechanism = _clean_text(label.get("clinical_pharmacology"))

        # Indications
        raw_indications = _clean_text(label.get("indications_and_usage"))
        indications = [raw_indications] if raw_indications else []

        # Dosage
        adult_dosage = _clean_text(label.get("dosage_and_administration"))
        pediatric_dosage = _clean_text(label.get("pediatric_use"))
        renal_adjustment = ""
        hepatic_adjustment = ""

        # Overdose information (from FDA "overdosage" section)
        overdose_info = _clean_text(label.get("overdosage"), max_len=3000)

        # Administration details (dosage forms, how supplied, storage)
        admin_parts = []
        dfs = _clean_text(label.get("dosage_forms_and_strengths"), max_len=1500)
        if dfs:
            admin_parts.append(dfs)
        how_sup = _clean_text(label.get("how_supplied"), max_len=1500)
        if how_sup:
            admin_parts.append(how_sup)
        storage = _clean_text(label.get("storage_and_handling"), max_len=800)
        if storage:
            admin_parts.append("Storage & Handling: " + storage)
        administration_info = "\n\n".join(admin_parts)

        # Try to extract renal/hepatic from dosage text or use-in-specific-populations
        specific_populations = _clean_text(label.get("use_in_specific_populations"))
        if specific_populations:
            sp_lower = specific_populations.lower()
            if "renal" in sp_lower:
                renal_match = re.search(r"(renal[^.]*\.(?:[^.]*\.)?)", sp_lower)
                if renal_match:
                    renal_adjustment = renal_match.group(0).strip().capitalize()
            if "hepatic" in sp_lower or "liver" in sp_lower:
                hepatic_match = re.search(r"(hepatic[^.]*\.(?:[^.]*\.)?)", sp_lower)
                if hepatic_match:
                    hepatic_adjustment = hepatic_match.group(0).strip().capitalize()

        # Safety — use warnings_and_cautions (OpenFDA uses this field, NOT "warnings")
        contraindications = _clean_text(label.get("contraindications"))
        black_box = _clean_text(label.get("boxed_warning"))

        # Warnings: prefer warnings_and_cautions over warnings
        warnings_text = _clean_text(label.get("warnings_and_cautions"))
        if not warnings_text:
            warnings_text = _clean_text(label.get("warnings"))
        # Append warnings to contraindications for richer safety data
        if warnings_text and not contraindications:
            contraindications = warnings_text
        elif warnings_text and contraindications:
            contraindications = contraindications + "\n\nADDITIONAL WARNINGS: " + warnings_text[:1500]

        # Adverse reactions
        adverse_reactions = _clean_text(label.get("adverse_reactions"), max_len=2000)
        if adverse_reactions and contraindications:
            contraindications = contraindications + "\n\nADVERSE REACTIONS: " + adverse_reactions[:1000]
        elif adverse_reactions:
            contraindications = "ADVERSE REACTIONS: " + adverse_reactions

        # Pregnancy & lactation — truncate to fit DB
        pregnancy_risk = _clean_text(label.get("pregnancy"), max_len=2000)
        if not pregnancy_risk:
            pregnancy_risk = _clean_text(label.get("teratogenic_effects"), max_len=2000)
        lactation_risk = _clean_text(label.get("nursing_mothers"), max_len=2000)
        if not lactation_risk:
            # Try use_in_specific_populations for lactation info
            if specific_populations and "lactat" in specific_populations.lower():
                lact_match = re.search(r"(lactat[^.]*\.(?:[^.]*\.)?(?:[^.]*\.)?)", specific_populations.lower())
                if lact_match:
                    lactation_risk = lact_match.group(0).strip().capitalize()

        # Pricing: extract what we can from OpenFDA metadata
        manufacturer_names = openfda.get("manufacturer_name", [])
        product_type = openfda.get("product_type", [])
        route = openfda.get("route", [])
        ndc_codes = openfda.get("product_ndc", [])

        # Determine if generic is available (multiple manufacturers = generic exists)
        generic_available = len(manufacturer_names) > 1 or any(
            "generic" in str(pt).lower() for pt in product_type
        )

        # Build an approximate cost description from available info
        route_str = ", ".join(route).lower() if route else ""
        approximate_cost = _estimate_cost(generic_name, drug_class, route_str, generic_available)

        # Build source URL — DailyMed search page (always works).
        # NOTE: We intentionally do NOT use openfda.spl_id here because those
        # set-id values are frequently stale/expired and redirect to the
        # DailyMed homepage.  The verification service will upgrade this to a
        # direct drug-page URL using the DailyMed adapter's validated setid.
        import urllib.parse
        source_url = (
            "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query="
            + urllib.parse.quote_plus(generic_name)
        )

        # Extract effective date from label
        effective_date, source_year = _parse_effective_date(label)

        # --- Fetch adverse event data from FAERS ---
        faers = _fetch_adverse_events(generic_name, self.delay_scale)

        # Extract interactions from the already-fetched label (avoids re-fetching)
        raw_interactions = _clean_text(label.get("drug_interactions"))
        interactions = _parse_interaction_text(raw_interactions) if raw_interactions else []

        return NormalizedDrugData(
            generic_name=generic_name.title(),
            brand_names=brand_names,
            drug_class=drug_class,
            mechanism_of_action=mechanism,
            indications=indications,
            adult_dosage=adult_dosage,
            pediatric_dosage=pediatric_dosage,
            renal_adjustment=renal_adjustment,
            hepatic_adjustment=hepatic_adjustment,
            overdose_info=overdose_info,
            administration_info=administration_info,
            contraindications=contraindications,
            black_box_warnings=black_box,
            pregnancy_risk=pregnancy_risk,
            lactation_risk=lactation_risk,
            interactions=interactions,
            approximate_cost=approximate_cost,
            generic_available=generic_available,
            adverse_event_count=faers.get("total_count"),
            adverse_event_serious_count=faers.get("serious_count"),
            top_adverse_reactions=faers.get("top_reactions", []),
            source_authority="FDA",
            source_document_title=f"FDA Drug Label – {generic_name.title()}",
            source_url=source_url,
            source_year=source_year,
            effective_date=effective_date,
            data_retrieved_at=datetime.utcnow().isoformat(),
        )

    def fetch_interactions(self, generic_name: str) -> list[dict]:
        """Fetch drug interactions from FDA label data."""
        params = {
            "search": f'openfda.generic_name:"{generic_name}"',
            "limit": 1,
        }
        data = self._api_get(params, LABEL_URL)
        if not data or "results" not in data:
            return []

        label = data["results"][0]
        raw = _clean_text(label.get("drug_interactions"))
        if not raw:
            return []

        return _parse_interaction_text(raw)


# ---- Shared interaction-text parser ----

# Words that look like drug names (capitalized) but are NOT drug names.
# This blacklist prevents "Table", "Concomitant", "Intervention", etc.
_NON_DRUG_WORDS = frozenset(w.lower() for w in [
    "Table", "Tables", "See", "Drug", "Drugs", "Interaction", "Interactions",
    "Concomitant", "Use", "Intervention", "Interventions", "Effect",
    "Effects", "Clinical", "Impact", "Example", "Examples", "Risk",
    "Monitor", "Monitoring", "Recommendation", "Recommendations",
    "Mechanism", "Warnings", "Warning", "Precaution", "Precautions",
    "Description", "May", "Can", "Should", "When", "Avoid", "The",
    "These", "There", "This", "Other", "Some", "Specific", "Certain",
    "Following", "Administration", "Dosage", "Management", "Patients",
    "Potential", "Information", "Note", "Important", "Based", "Data",
    "Studies", "Study", "Results", "Increased", "Decreased", "However",
    "Although", "Because", "Therefore", "Particularly", "Combination",
    "Combinations", "Concurrent", "Coadministration", "Pharmacokinetic",
    "Pharmacodynamic", "Efficacy", "Safety", "With", "Section",
])


def _parse_interaction_text(raw: str) -> list[dict]:
    """
    Parse FDA / DailyMed drug-interaction free-text into structured entries.
    Uses a smarter heuristic:
      1. Split on bullet / numbered-list patterns and bold-like headers.
      2. Extract the first capitalized multi-letter word that is NOT in the
         blacklist — that is likely the interacting drug.
      3. If no valid drug name is found, skip the segment entirely.
    """
    interactions: list[dict] = []
    seen_drugs: set[str] = set()

    # Split into segments using common label delimiters:
    #   • Numbered items: "7.1 Metformin", "• Warfarin", "- Lithium"
    #   • Lines starting with a capitalized drug-like word followed by colon/dash
    segments = re.split(
        r"(?:(?<=\n)|(?<=\. ))(?=(?:\d{1,2}(?:\.\d+)?\s+)?[A-Z][a-z])",
        raw,
    )

    # Also try splitting on bullet-style patterns
    if len(segments) <= 2:
        segments = re.split(r"[•\-–]\s+", raw)

    for segment in segments:
        segment = segment.strip()
        if len(segment) < 15:
            continue

        # Try to extract drug name: first capitalized word/phrase not in blacklist
        # Patterns: "Warfarin:", "Metformin -", "Lithium (see Warnings)", "ACE Inhibitors"
        drug_match = re.match(
            r"(?:\d{1,2}(?:\.\d+)?\s+)?"          # optional section number
            r"([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+){0,3})"  # 1-4 capitalized words
            r"\s*[:\-–(]",                          # followed by separator
            segment,
        )
        if not drug_match:
            # Try without separator — just capitalized word(s) at start
            drug_match = re.match(
                r"(?:\d{1,2}(?:\.\d+)?\s+)?"
                r"([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+){0,2})"
                r"\s+(?:may|can|should|is|are|has|increases?|decreases?|affects?|inhibits?|induces?|reduces?|enhances?|potentiates?)\b",
                segment,
            )

        if not drug_match:
            continue

        drug_name = drug_match.group(1).strip()
        # Validate: skip if ALL words are in the blacklist
        name_words = drug_name.split()
        valid_words = [w for w in name_words if w.lower() not in _NON_DRUG_WORDS]
        if not valid_words:
            continue
        # Rebuild drug name from valid words
        drug_name = " ".join(name_words)  # keep original casing

        # Skip very short or already-seen
        if len(drug_name) < 3:
            continue
        name_key = drug_name.lower()
        if name_key in seen_drugs:
            continue
        seen_drugs.add(name_key)

        # Build description from the rest of the segment
        desc = segment[drug_match.end():].strip(" :-–")
        if not desc:
            desc = segment
        desc = desc[:500]

        interactions.append({
            "interacting_drug": drug_name,
            "severity": _extract_severity(segment),
            "description": desc,
        })

    return interactions[:20]  # Cap at 20 interactions


def get_fda_drug_list(skip: int = 0, limit: int = 100) -> list[str]:
    """
    Return a curated list of the most commonly prescribed drugs for
    initial discovery.  The previous approach (using OpenFDA
    ``count=openfda.generic_name.exact``) returned alphabetically,
    which was dominated by OTC/cosmetic products.  This curated list
    ensures that the bootstrap populates clinically important drugs first.

    The list is based on the 100 most dispensed prescription medications
    in the United States (CMS / IQVIA / GoodRx publicly available data).
    """
    CURATED_DRUGS = [
        # Cardiovascular
        "Lisinopril", "Amlodipine", "Atorvastatin", "Losartan", "Metoprolol",
        "Hydrochlorothiazide", "Simvastatin", "Rosuvastatin", "Pravastatin",
        "Carvedilol", "Valsartan", "Furosemide", "Spironolactone", "Warfarin",
        "Clopidogrel", "Apixaban", "Rivaroxaban", "Diltiazem", "Lisinopril",
        "Enalapril",
        # Diabetes
        "Metformin", "Glipizide", "Glyburide", "Sitagliptin", "Empagliflozin",
        "Insulin Glargine", "Liraglutide", "Pioglitazone", "Semaglutide",
        "Dapagliflozin",
        # Respiratory
        "Albuterol", "Montelukast", "Fluticasone", "Tiotropium", "Budesonide",
        "Cetirizine", "Loratadine", "Fexofenadine", "Prednisone", "Prednisolone",
        # Pain / Inflammation
        "Ibuprofen", "Acetaminophen", "Naproxen", "Meloxicam", "Celecoxib",
        "Gabapentin", "Pregabalin", "Tramadol", "Cyclobenzaprine", "Diclofenac",
        # Mental Health
        "Sertraline", "Escitalopram", "Fluoxetine", "Duloxetine", "Venlafaxine",
        "Bupropion", "Trazodone", "Citalopram", "Paroxetine", "Mirtazapine",
        "Aripiprazole", "Quetiapine", "Risperidone", "Olanzapine", "Lithium",
        "Alprazolam", "Lorazepam", "Clonazepam", "Buspirone", "Hydroxyzine",
        # Gastrointestinal
        "Omeprazole", "Pantoprazole", "Esomeprazole", "Famotidine",
        "Ondansetron", "Metoclopramide", "Sucralfate", "Dicyclomine",
        "Loperamide", "Docusate",
        # Endocrine / Thyroid
        "Levothyroxine", "Methimazole",
        # Antibiotics / Anti-infectives
        "Amoxicillin", "Azithromycin", "Ciprofloxacin", "Levofloxacin",
        "Doxycycline", "Metronidazole", "Cephalexin", "Sulfamethoxazole",
        "Clindamycin", "Nitrofurantoin", "Fluconazole", "Valacyclovir",
        "Acyclovir",
        # Neurological
        "Levetiracetam", "Topiramate", "Lamotrigine", "Carbamazepine",
        "Sumatriptan", "Donepezil", "Memantine",
        # Other common Rx
        "Tamsulosin", "Finasteride", "Sildenafil", "Tadalafil",
        "Latanoprost", "Timolol", "Cyclosporine",
        "Allopurinol", "Colchicine", "Methotrexate",
    ]
    # Deduplicate while preserving order
    seen = set()
    unique: list[str] = []
    for d in CURATED_DRUGS:
        key = d.lower()
        if key not in seen:
            seen.add(key)
            unique.append(d)

    # Apply pagination
    return unique[skip:skip + limit]
