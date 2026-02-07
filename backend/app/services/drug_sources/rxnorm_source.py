"""
NIH RxNorm + RxNav API adapter.
Sources:
  - RxNorm: https://rxnav.nlm.nih.gov/RxNormAPIs.html
  - RxClass: https://rxnav.nlm.nih.gov/RxClassAPIs.html
Authority: National Library of Medicine (NLM) / NIH
Free, no API key required.

NOTE: The legacy RxNav Interaction API (/REST/interaction/) was sunset.
Interactions are now obtained from the OpenFDA / DailyMed label text.
RxNorm's primary value is drug classification and nomenclature.
"""

import logging
import time
from datetime import datetime
from typing import Optional

import requests

from app.services.drug_sources.base_source import DrugDataSource, NormalizedDrugData

logger = logging.getLogger("clerasense.sources.rxnorm")

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
SEARCH_DELAY = 0.5


class RxNormSource(DrugDataSource):
    """Fetch drug classification and nomenclature data from NIH RxNorm/RxNav."""

    def __init__(self, delay_scale: float = 1.0):
        self.delay_scale = delay_scale

    @property
    def source_name(self) -> str:
        return "NIH RxNorm / RxNav API"

    @property
    def source_authority(self) -> str:
        return "NIH/NLM"

    def _api_get(self, url: str, params: dict = None) -> Optional[dict]:
        """Rate-limited GET request."""
        try:
            time.sleep(SEARCH_DELAY * self.delay_scale)
            resp = requests.get(url, params=params or {}, timeout=30)
            if resp.status_code == 200:
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct or "javascript" in ct:
                    return resp.json()
                # Try parsing as JSON anyway (some responses lack proper Content-Type)
                try:
                    return resp.json()
                except Exception:
                    return None
            return None
        except requests.RequestException as exc:
            logger.error("RxNorm request failed: %s", exc)
            return None

    def _get_rxcui(self, drug_name: str) -> Optional[str]:
        """Look up the RxCUI (concept ID) for a drug name."""
        data = self._api_get(f"{RXNORM_BASE}/rxcui.json", {
            "name": drug_name,
            "search": 2,  # Normalized search
        })
        if not data:
            return None

        id_group = data.get("idGroup", {})
        rxnorm_ids = id_group.get("rxnormId", [])
        return rxnorm_ids[0] if rxnorm_ids else None

    def search_drugs(self, query: str, limit: int = 10) -> list[str]:
        """Search RxNorm for drugs matching a query."""
        data = self._api_get(f"{RXNORM_BASE}/approximateTerm.json", {
            "term": query,
            "maxEntries": min(limit, 20),
        })
        if not data:
            return []

        candidates = data.get("approximateGroup", {}).get("candidate", [])
        names = set()
        for c in candidates:
            rxcui = c.get("rxcui")
            if rxcui:
                name_data = self._api_get(f"{RXNORM_BASE}/rxcui/{rxcui}/properties.json")
                if name_data:
                    props = name_data.get("properties", {})
                    name = props.get("name", "").strip().title()
                    if name and len(name) > 2:
                        names.add(name)
        return list(names)[:limit]

    def fetch_drug_data(self, generic_name: str) -> Optional[NormalizedDrugData]:
        """
        Fetch drug classification data from RxNorm.
        RxNorm provides:
        - Normalized names & brand/generic relationships
        - Drug classes (via RxClass: ATC, MeSH)
        - Whether generic formulations exist
        """
        rxcui = self._get_rxcui(generic_name)
        if not rxcui:
            return None

        # Get properties
        props_data = self._api_get(f"{RXNORM_BASE}/rxcui/{rxcui}/properties.json")
        if not props_data:
            return None

        props = props_data.get("properties", {})
        normalized_name = props.get("name", generic_name).strip().title()

        # Get brand names (related brands)
        brand_names = []
        related_data = self._api_get(f"{RXNORM_BASE}/rxcui/{rxcui}/related.json", {
            "tty": "BN",  # Brand Name
        })
        if related_data:
            for group in related_data.get("relatedGroup", {}).get("conceptGroup", []):
                for prop in group.get("conceptProperties", []):
                    bn = prop.get("name", "").strip().title()
                    if bn:
                        brand_names.append(bn)

        # Determine generic availability: if there are SBD (Semantic Branded Drug)
        # AND SCD (Semantic Clinical Drug) entries, generic exists
        generic_available = False
        all_related = self._api_get(f"{RXNORM_BASE}/rxcui/{rxcui}/allrelated.json")
        if all_related:
            groups = all_related.get("allRelatedGroup", {}).get("conceptGroup", [])
            ttys = {g.get("tty") for g in groups if g.get("conceptProperties")}
            # SCD = generic clinical drug, SBD = branded drug
            if "SCD" in ttys or "GPCK" in ttys:
                generic_available = True

        # Get drug class via RxClass
        drug_class = ""
        combo_hints = ["combination", " and ", " with "]
        class_data = self._api_get(f"{RXNORM_BASE}/rxclass/class/byRxcui.json", {
            "rxcui": rxcui,
            "relaSource": "ATC",
        })
        if class_data:
            classes = class_data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
            # Prefer a class that is NOT about combinations
            single_classes = []
            combo_classes = []
            for c in classes:
                name = c.get("rxclassMinConceptItem", {}).get("className", "")
                if name:
                    if any(kw in name.lower() for kw in combo_hints):
                        combo_classes.append(name)
                    else:
                        single_classes.append(name)
            drug_class = single_classes[0] if single_classes else (combo_classes[0] if combo_classes else "")

        # If ATC didn't work or returned a combo class, try MeSH
        if not drug_class or any(kw in drug_class.lower() for kw in combo_hints):
            class_data = self._api_get(f"{RXNORM_BASE}/rxclass/class/byRxcui.json", {
                "rxcui": rxcui,
                "relaSource": "MESH",
            })
            if class_data:
                classes = class_data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
                for c in classes:
                    name = c.get("rxclassMinConceptItem", {}).get("className", "")
                    if name and not any(kw in name.lower() for kw in combo_hints):
                        drug_class = name
                        break

        return NormalizedDrugData(
            generic_name=normalized_name,
            brand_names=brand_names[:10],
            drug_class=drug_class,
            generic_available=generic_available if generic_available else None,
            source_authority="NIH/NLM",
            source_document_title=f"RxNorm Drug Concept – {normalized_name} (RXCUI: {rxcui})",
            source_url=f"https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm={rxcui}",
            source_year=datetime.now().year,
            data_retrieved_at=datetime.utcnow().isoformat(),
        )

    def fetch_interactions(self, generic_name: str) -> list[dict]:
        """
        RxNorm's standalone Interaction API has been sunset.
        Interactions are obtained from FDA/DailyMed label text instead.
        This method returns an empty list to signal that RxNorm doesn't
        provide interaction data directly, without causing errors.
        """
        return []
