"""
NIH DailyMed API adapter.
Source: https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm
Authority: National Library of Medicine (NLM) / NIH
Free, no API key required.

NOTE: The DailyMed v2 /sections.json endpoint is currently returning HTML
instead of JSON.  This adapter therefore uses only the SPL search / drugname
endpoints that DO return proper JSON, and supplements label content by
fetching the SPL XML zip when available.
"""

import logging
import re
import time
import io
import zipfile
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree

import requests

from app.services.drug_sources.base_source import DrugDataSource, NormalizedDrugData
from app.services.drug_sources.openfda_source import _parse_interaction_text

logger = logging.getLogger("clerasense.sources.dailymed")

BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services"
SEARCH_DELAY = 1.0

# SPL XML section code → human-readable key
_SECTION_CODES = {
    "34067-9": "indications_and_usage",
    "34068-7": "dosage_and_administration",
    "34070-3": "contraindications",
    "43685-7": "warnings_and_precautions",
    "34071-1": "warnings",
    "34084-4": "adverse_reactions",
    "34073-7": "drug_interactions",
    "42228-7": "pregnancy",
    "34080-2": "nursing_mothers",
    "34081-0": "pediatric_use",
    "34082-8": "geriatric_use",
    "34088-5": "overdosage",
    "34090-1": "clinical_pharmacology",
    "43679-0": "mechanism_of_action",
    "34066-1": "boxed_warning",
    "42229-5": "spl_medguide",
    "34069-5": "how_supplied",
    "43684-0": "use_in_specific_populations",
}


def _clean_xml_text(text: str | None) -> str:
    """Strip XML/HTML tags and normalize whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 3000:
        cleaned = cleaned[:3000] + "..."
    return cleaned


def _extract_text_from_element(elem) -> str:
    """Recursively extract all text from an XML element."""
    return "".join(elem.itertext())


class DailyMedSource(DrugDataSource):
    """Fetch structured product labeling data from NIH DailyMed."""

    def __init__(self, delay_scale: float = 1.0):
        self.delay_scale = delay_scale

    @property
    def source_name(self) -> str:
        return "NIH DailyMed API"

    @property
    def source_authority(self) -> str:
        return "NIH/NLM"

    def _api_get_json(self, endpoint: str, params: dict) -> Optional[dict]:
        """Rate-limited JSON GET to DailyMed."""
        try:
            time.sleep(SEARCH_DELAY * self.delay_scale)
            url = f"{BASE_URL}/{endpoint}"
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct or "javascript" in ct:
                    return resp.json()
                # Sometimes DailyMed returns HTML even for .json URLs
                logger.debug("DailyMed returned non-JSON Content-Type: %s", ct)
                return None
            if resp.status_code == 404:
                return None
            logger.warning("DailyMed %s returned %s", endpoint, resp.status_code)
            return None
        except Exception as exc:
            logger.error("DailyMed request failed: %s", exc)
            return None

    def search_drugs(self, query: str, limit: int = 10) -> list[str]:
        """Search DailyMed for SPLs matching a drug name."""
        data = self._api_get_json("v2/spls.json", {
            "drug_name": query,
            "page": 1,
            "pagesize": min(limit, 100),
        })
        if not data or "data" not in data:
            return []

        names = set()
        for item in data["data"]:
            title = item.get("title", "")
            parts = re.split(r"\s*[-–]\s*", title)
            if parts:
                name = parts[0].strip().title()
                if name and len(name) > 2:
                    names.add(name)
        return list(names)[:limit]

    def _get_spl_setid(self, generic_name: str) -> Optional[str]:
        """
        Find the best SPL set_id for a single-ingredient drug.

        Fetches multiple results from DailyMed and scores them to prefer
        exact single-ingredient matches over combination products, brand
        bundles, or unrelated name collisions (e.g. hand sanitizer for
        "ethane").
        """
        data = self._api_get_json("v2/spls.json", {
            "drug_name": generic_name,
            "page": 1,
            "pagesize": 25,
        })
        if not data or "data" not in data or not data["data"]:
            return None

        name_lower = generic_name.lower().strip()
        # Common salt forms that are equivalent to the base drug
        salt_suffixes = [
            "hydrochloride", "hcl", "sulfate", "sodium", "potassium",
            "maleate", "besylate", "mesylate", "fumarate", "tartrate",
            "succinate", "calcium", "acetate", "phosphate", "citrate",
            "dihydrate", "anhydrous", "trihydrate",
        ]
        salt_forms = [f"{name_lower} {s}" for s in salt_suffixes]

        # Dosage form keywords — commas within these are NOT combo indicators
        dosage_forms = [
            "tablet", "capsule", "solution", "injection", "cream",
            "ointment", "powder", "suspension", "aerosol", "spray",
            "patch", "gel", "drops", "inhaler", "suppository", "lozenge",
            "syrup", "elixir", "emulsion", "pellet", "granule", "kit",
        ]
        # Words that signal the product is NOT a pharmaceutical drug
        non_drug_words = [
            "sanitizer", "hand wash", "antiseptic", "disinfectant",
            "cleaning", "cosmetic", "sunscreen", "soap", "shampoo",
            "toothpaste", "mouthwash", "deodorant",
        ]

        best_setid = None
        best_score = -9999

        for item in data["data"]:
            title = (item.get("title") or "").strip()
            title_lower = title.lower()
            setid = item.get("setid")
            if not setid:
                continue

            score = 0

            # ---- Disqualify non-pharmaceutical products ----
            if any(nw in title_lower for nw in non_drug_words):
                score -= 500

            # ---- Extract the drug-name portion ----
            # DailyMed title formats:
            #   "DRUG NAME- dosage form [MANUFACTURER]"
            #   "DRUG NAME SALT FORM TABLET, FILM COATED [MANUFACTURER]"
            # First split off manufacturer bracket
            mfr_split = re.split(r"\s*\[", title_lower, maxsplit=1)
            name_and_form = mfr_split[0].strip()

            # Split off dash-separated dosage description
            dash_parts = re.split(r"\s*[-–]\s*", name_and_form, maxsplit=1)
            drug_portion = dash_parts[0].strip()

            # Further isolate the drug name from dosage form words
            # e.g., "atorvastatin calcium tablet" -> "atorvastatin calcium"
            drug_name_part = drug_portion
            for df in dosage_forms:
                idx = drug_name_part.find(df)
                if idx > 0:
                    drug_name_part = drug_name_part[:idx].strip().rstrip(",").strip()
                    break

            # ---- Check for combination in the drug name portion only ----
            # "and" or "/" in the drug NAME part (not dosage) = combination
            is_combo = (" and " in drug_name_part or " / " in drug_name_part
                        or ("," in drug_name_part
                            and not any(s in drug_name_part for s in salt_suffixes)))

            # ---- Scoring ----
            if drug_name_part == name_lower:
                score += 300   # Perfect single-ingredient match
            elif drug_name_part in salt_forms:
                score += 280   # Salt form exact match
            elif drug_name_part.startswith(name_lower) and not is_combo:
                # e.g., "atorvastatin calcium" when searching "atorvastatin"
                score += 260
            elif name_lower in drug_name_part and not is_combo:
                score += 100   # Name appears within drug portion
            elif name_lower in drug_name_part and is_combo:
                score -= 100   # Combo product containing our drug
            elif name_lower not in title_lower:
                score -= 300   # Drug name doesn't even appear in title

            # Heavy penalty for combos
            if is_combo:
                score -= 200

            # Prefer shorter titles (less likely to be complex products)
            if len(title) < 80:
                score += 10
            elif len(title) > 140:
                score -= 10

            if score > best_score:
                best_score = score
                best_setid = setid

        # Only return if the best match actually seems relevant
        return best_setid if best_score > -200 else None

    def _fetch_spl_xml_sections(self, setid: str) -> dict[str, str]:
        """
        Download the SPL XML zip from DailyMed and parse labeled sections.
        This is the reliable way to get section content since the REST
        /sections.json endpoint currently returns HTML.
        """
        sections: dict[str, str] = {}
        try:
            time.sleep(SEARCH_DELAY * self.delay_scale)
            zip_url = f"https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?setid={setid}&type=zip&name={setid}"
            resp = requests.get(zip_url, timeout=45)
            if resp.status_code != 200:
                logger.debug("DailyMed ZIP download returned %s for setid %s", resp.status_code, setid)
                return sections

            # Parse the ZIP
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_files = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                if not xml_files:
                    return sections
                with zf.open(xml_files[0]) as xf:
                    tree = ElementTree.parse(xf)

            root = tree.getroot()
            # SPL XML uses the urn:hl7-org:v3 namespace
            ns = {"hl7": "urn:hl7-org:v3"}

            for component in root.findall(".//hl7:component/hl7:section", ns):
                code_elem = component.find("hl7:code", ns)
                if code_elem is None:
                    continue
                code = code_elem.get("code", "")
                section_key = _SECTION_CODES.get(code)
                if not section_key:
                    continue
                # Extract all text from <text> sub-element
                text_elem = component.find("hl7:text", ns)
                if text_elem is not None:
                    raw_text = ElementTree.tostring(text_elem, encoding="unicode", method="text")
                    sections[section_key] = raw_text.strip()

        except zipfile.BadZipFile:
            logger.debug("DailyMed ZIP was invalid for setid %s", setid)
        except Exception as exc:
            logger.warning("DailyMed XML parse failed for %s: %s", setid, exc)

        return sections

    def fetch_drug_data(self, generic_name: str) -> Optional[NormalizedDrugData]:
        """Fetch drug label data from DailyMed SPL XML."""
        setid = self._get_spl_setid(generic_name)
        if not setid:
            return None

        # Fetch sections from the actual SPL XML (reliable)
        sections = self._fetch_spl_xml_sections(setid)

        if not sections:
            # Even if we can't get sections, return a minimal record
            # confirming the drug exists in DailyMed (helps verification)
            return NormalizedDrugData(
                generic_name=generic_name.title(),
                source_authority="NIH/NLM",
                source_document_title=f"DailyMed SPL – {generic_name.title()}",
                source_url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
                source_year=datetime.now().year,
                data_retrieved_at=datetime.utcnow().isoformat(),
            )

        # Map parsed sections to NormalizedDrugData fields
        indications = _clean_xml_text(sections.get("indications_and_usage", ""))
        dosage = _clean_xml_text(sections.get("dosage_and_administration", ""))
        contraindications = _clean_xml_text(sections.get("contraindications", ""))
        warnings = _clean_xml_text(sections.get("warnings_and_precautions", ""))
        if not warnings:
            warnings = _clean_xml_text(sections.get("warnings", ""))
        boxed = _clean_xml_text(sections.get("boxed_warning", ""))
        pregnancy = _clean_xml_text(sections.get("pregnancy", ""))
        if not pregnancy:
            pregnancy = _clean_xml_text(sections.get("use_in_specific_populations", ""))
        nursing = _clean_xml_text(sections.get("nursing_mothers", ""))
        mechanism = _clean_xml_text(sections.get("mechanism_of_action", ""))
        if not mechanism:
            mechanism = _clean_xml_text(sections.get("clinical_pharmacology", ""))
        drug_interactions_text = _clean_xml_text(sections.get("drug_interactions", ""))
        interactions = _parse_interaction_text(drug_interactions_text) if drug_interactions_text else []
        adverse = _clean_xml_text(sections.get("adverse_reactions", ""))
        overdosage = _clean_xml_text(sections.get("overdosage", ""))
        how_supplied = _clean_xml_text(sections.get("how_supplied", ""))
        administration_info = how_supplied[:3000] if how_supplied else ""

        # Enrich contraindications with warnings & adverse reactions
        if warnings and contraindications:
            contraindications = contraindications + "\n\nWARNINGS: " + warnings[:1500]
        elif warnings:
            contraindications = warnings

        if adverse and contraindications:
            contraindications = contraindications + "\n\nADVERSE REACTIONS: " + adverse[:1000]
        elif adverse:
            contraindications = "ADVERSE REACTIONS: " + adverse

        if len(pregnancy) > 2000:
            pregnancy = pregnancy[:2000] + "..."
        if len(nursing) > 2000:
            nursing = nursing[:2000] + "..."

        source_url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"

        return NormalizedDrugData(
            generic_name=generic_name.title(),
            brand_names=[],
            drug_class="",
            mechanism_of_action=mechanism,
            indications=[indications] if indications else [],
            adult_dosage=dosage,
            overdose_info=overdosage,
            administration_info=administration_info,
            contraindications=contraindications,
            black_box_warnings=boxed,
            pregnancy_risk=pregnancy,
            lactation_risk=nursing,
            interactions=interactions,
            source_authority="NIH/NLM",
            source_document_title=f"DailyMed SPL – {generic_name.title()}",
            source_url=source_url,
            source_year=datetime.now().year,
            data_retrieved_at=datetime.utcnow().isoformat(),
        )

    def fetch_interactions(self, generic_name: str) -> list[dict]:
        """Fetch interactions from DailyMed SPL DRUG INTERACTIONS section."""
        setid = self._get_spl_setid(generic_name)
        if not setid:
            return []

        sections = self._fetch_spl_xml_sections(setid)
        raw = _clean_xml_text(sections.get("drug_interactions", ""))
        if not raw:
            return []

        # Use the shared smart interaction parser
        return _parse_interaction_text(raw)
