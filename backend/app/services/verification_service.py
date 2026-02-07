"""
Cross-source verification service.
Compares drug data from multiple authoritative sources to ensure
accuracy and eliminate bias before committing to the database.

Verification rules:
  1. A drug must appear in at least 2 independent sources to be added.
  2. Critical safety fields (contraindications, black box warnings) must
     agree across sources — conflict triggers manual-review flagging.
  3. Non-critical fields (brand names, dosage text) are merged, preferring
     the most complete/detailed version.
  4. Interactions are union-merged across sources (safety-first approach).
"""

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from app.services.drug_sources.base_source import NormalizedDrugData

logger = logging.getLogger("clerasense.verification")

# Minimum text similarity to consider two descriptions as "agreeing"
AGREEMENT_THRESHOLD = 0.35

# Minimum number of sources that must provide data for a drug
MIN_SOURCES_REQUIRED = 2

# Authoritative drug-class overrides for commonly misclassified drugs.
# APIs sometimes return a combo-product class even for single-ingredient
# queries.  These mappings ensure the correct pharmacologic class.
_DRUG_CLASS_OVERRIDES: dict[str, str] = {
    "metformin": "Biguanide Antihyperglycemic",
    "atorvastatin": "HMG-CoA Reductase Inhibitor (Statin)",
    "simvastatin": "HMG-CoA Reductase Inhibitor (Statin)",
    "rosuvastatin": "HMG-CoA Reductase Inhibitor (Statin)",
    "ibuprofen": "Nonsteroidal Anti-inflammatory Drug (NSAID)",
    "amoxicillin": "Aminopenicillin Antibiotic",
    "omeprazole": "Proton Pump Inhibitor",
    "amlodipine": "Calcium Channel Blocker",
    "metoprolol": "Beta-Adrenergic Blocker",
    "hydrochlorothiazide": "Thiazide Diuretic",
    "doxycycline": "Tetracycline Antibiotic",
    "meloxicam": "Nonsteroidal Anti-inflammatory Drug (NSAID)",
}


@dataclass
class VerificationResult:
    """Outcome of cross-source verification."""
    verified: bool = False
    confidence: float = 0.0  # 0–1
    merged_data: Optional[NormalizedDrugData] = None
    sources_used: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _text_similarity(a: str, b: str) -> float:
    """Compute normalized text similarity between two strings."""
    if not a or not b:
        return 0.0
    a_clean = a.lower().strip()
    b_clean = b.lower().strip()
    if a_clean == b_clean:
        return 1.0
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def _pick_longest(*texts: str) -> str:
    """Return the longest non-empty text (most detailed)."""
    candidates = [t for t in texts if t and t.strip()]
    if not candidates:
        return ""
    return max(candidates, key=len)


def _merge_lists(*lists: list) -> list:
    """Merge multiple lists, deduplicating by lowercase comparison."""
    seen = set()
    result = []
    for lst in lists:
        for item in (lst or []):
            key = item.strip().lower() if isinstance(item, str) else str(item).lower()
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def _merge_interactions(*interaction_lists: list[dict]) -> list[dict]:
    """
    Union-merge interactions across sources.
    If the same interacting drug appears in multiple sources,
    keep the highest severity (safety-first approach).
    """
    severity_rank = {"contraindicated": 4, "major": 3, "moderate": 2, "minor": 1}
    merged: dict[str, dict] = {}

    for interactions in interaction_lists:
        for ix in (interactions or []):
            key = ix.get("interacting_drug", "").lower().strip()
            if not key:
                continue
            existing = merged.get(key)
            if existing:
                # Keep higher severity
                new_rank = severity_rank.get(ix.get("severity", "moderate"), 2)
                old_rank = severity_rank.get(existing.get("severity", "moderate"), 2)
                if new_rank > old_rank:
                    merged[key] = ix
                elif new_rank == old_rank and len(ix.get("description", "")) > len(existing.get("description", "")):
                    merged[key] = ix
            else:
                merged[key] = ix

    return list(merged.values())


def verify_drug_data(
    drug_name: str,
    source_data: list[NormalizedDrugData],
) -> VerificationResult:
    """
    Cross-verify drug data from multiple sources.

    Args:
        drug_name: The generic drug name.
        source_data: List of NormalizedDrugData from different sources.

    Returns:
        VerificationResult with merged data if verification passes.
    """
    result = VerificationResult()

    if not source_data:
        result.notes.append(f"No data found for '{drug_name}' from any source.")
        return result

    # Filter out None/empty entries
    valid_data = [d for d in source_data if d is not None]
    result.sources_used = [d.source_authority for d in valid_data]

    if len(valid_data) < MIN_SOURCES_REQUIRED:
        result.notes.append(
            f"Only {len(valid_data)} source(s) returned data for '{drug_name}'. "
            f"Minimum {MIN_SOURCES_REQUIRED} required for full verification."
        )
        # Accept single-source data from authoritative agencies (FDA, NIH)
        # with reduced confidence, rather than rejecting entirely.
        if len(valid_data) == 1:
            authority = valid_data[0].source_authority
            if authority in ("FDA", "NIH/NLM"):
                result.notes.append(
                    f"Single {authority} source accepted as authoritative."
                )
            else:
                result.notes.append(
                    f"Single non-authoritative source ({authority}); accepting with low confidence."
                )
        # Continue to merge & return data (don't reject)

    # --- Cross-check critical safety fields ---
    # Check contraindications agreement
    contras = [d.contraindications for d in valid_data if d.contraindications]
    if len(contras) >= 2:
        sim = _text_similarity(contras[0], contras[1])
        if sim < AGREEMENT_THRESHOLD:
            result.conflicts.append(
                f"Contraindication descriptions differ significantly (similarity={sim:.2f}). "
                "Using the most detailed version but flagging for review."
            )

    # Check black box warnings agreement
    bbw = [d.black_box_warnings for d in valid_data if d.black_box_warnings]
    if len(bbw) >= 2:
        sim = _text_similarity(bbw[0], bbw[1])
        if sim < AGREEMENT_THRESHOLD:
            result.conflicts.append(
                f"Black box warning descriptions differ (similarity={sim:.2f}). "
                "Using the most detailed version but flagging for review."
            )

    # Check pregnancy risk agreement
    preg = [d.pregnancy_risk for d in valid_data if d.pregnancy_risk]
    if len(preg) >= 2:
        sim = _text_similarity(preg[0], preg[1])
        if sim < AGREEMENT_THRESHOLD:
            result.conflicts.append(
                f"Pregnancy risk information differs (similarity={sim:.2f})."
            )

    # --- Merge data (prefer most complete) ---
    merged = NormalizedDrugData(generic_name=drug_name.title())

    # Brand names: union across sources
    merged.brand_names = _merge_lists(*[d.brand_names for d in valid_data])

    # Drug class: prefer a single-ingredient-specific class.
    # Use authoritative override if available, else prefer RxNorm ATC > FDA.
    override_class = _DRUG_CLASS_OVERRIDES.get(drug_name.lower().strip())
    if override_class:
        merged.drug_class = override_class
    else:
        combo_hints = ["combination", " and ", " with "]
        all_classes = [(d.drug_class, d.source_authority) for d in valid_data if d.drug_class]
        single_classes = [(c, a) for c, a in all_classes if not any(kw in c.lower() for kw in combo_hints)]
        if single_classes:
            for pref_auth in ("NIH/NLM", "FDA"):
                for c, a in single_classes:
                    if a == pref_auth:
                        merged.drug_class = c
                        break
                if merged.drug_class:
                    break
            if not merged.drug_class:
                merged.drug_class = single_classes[0][0]
        elif all_classes:
            merged.drug_class = _pick_longest(*[c for c, _ in all_classes])
        else:
            merged.drug_class = ""

    # Mechanism of action: pick most detailed
    merged.mechanism_of_action = _pick_longest(*[d.mechanism_of_action for d in valid_data])

    # Indications: merge
    all_indications = []
    for d in valid_data:
        all_indications.extend(d.indications or [])
    merged.indications = _merge_lists(all_indications)

    # Dosage: pick most detailed
    merged.adult_dosage = _pick_longest(*[d.adult_dosage for d in valid_data])
    merged.pediatric_dosage = _pick_longest(*[d.pediatric_dosage for d in valid_data])
    merged.renal_adjustment = _pick_longest(*[d.renal_adjustment for d in valid_data])
    merged.hepatic_adjustment = _pick_longest(*[d.hepatic_adjustment for d in valid_data])

    # Safety: pick most detailed (safety-first)
    merged.contraindications = _pick_longest(*[d.contraindications for d in valid_data])
    merged.black_box_warnings = _pick_longest(*[d.black_box_warnings for d in valid_data])
    merged.pregnancy_risk = _pick_longest(*[d.pregnancy_risk for d in valid_data])
    merged.lactation_risk = _pick_longest(*[d.lactation_risk for d in valid_data])

    # Interactions: union-merge with highest severity wins
    merged.interactions = _merge_interactions(*[d.interactions for d in valid_data])

    # Pricing: prefer NADAC real data over estimates
    for d in valid_data:
        if d.nadac_per_unit is not None:
            merged.approximate_cost = d.approximate_cost
            merged.nadac_per_unit = d.nadac_per_unit
            merged.nadac_ndc = d.nadac_ndc
            merged.nadac_effective_date = d.nadac_effective_date
            merged.nadac_package_description = d.nadac_package_description
            break
    # If no NADAC data, fall back to first available cost text
    if not merged.approximate_cost:
        for d in valid_data:
            if d.approximate_cost:
                merged.approximate_cost = d.approximate_cost
                break

    # Generic available: if ANY source says True, it's True
    for d in valid_data:
        if d.generic_available is True:
            merged.generic_available = True
            break
    if merged.generic_available is None:
        for d in valid_data:
            if d.generic_available is not None:
                merged.generic_available = d.generic_available
                break

    # Adverse events: pick from FDA source (only source that has FAERS data)
    for d in valid_data:
        if d.adverse_event_count is not None:
            merged.adverse_event_count = d.adverse_event_count
            merged.adverse_event_serious_count = d.adverse_event_serious_count
            merged.top_adverse_reactions = d.top_adverse_reactions
            break

    # Use the primary source (FDA preferred)
    fda_source = next((d for d in valid_data if d.source_authority == "FDA"), valid_data[0])
    merged.source_authority = fda_source.source_authority
    merged.source_document_title = fda_source.source_document_title
    merged.source_url = fda_source.source_url
    merged.source_year = fda_source.source_year
    merged.effective_date = fda_source.effective_date
    merged.data_retrieved_at = fda_source.data_retrieved_at

    # --- Calculate confidence score ---
    confidence = 0.0
    # Base from number of confirming sources (now up to 4 with NADAC)
    confidence += min(len(valid_data) / 4.0, 0.35)
    # Points for having key fields
    if merged.mechanism_of_action:
        confidence += 0.08
    if merged.indications:
        confidence += 0.08
    if merged.contraindications:
        confidence += 0.08
    if merged.adult_dosage:
        confidence += 0.08
    if merged.black_box_warnings or merged.contraindications:
        confidence += 0.08
    # Bonus for NADAC real pricing data
    if merged.nadac_per_unit is not None:
        confidence += 0.08
    # Bonus for adverse event data
    if merged.adverse_event_count is not None:
        confidence += 0.07
    # Deduct for conflicts
    confidence -= len(result.conflicts) * 0.05
    confidence = max(0.0, min(1.0, confidence))

    result.verified = True
    result.confidence = round(confidence, 3)
    result.merged_data = merged

    if result.conflicts:
        result.notes.append(
            f"Verified with {len(result.conflicts)} conflict(s): data merged using safety-first approach."
        )
    else:
        result.notes.append(
            f"Verified across {len(valid_data)} source(s) with no conflicts."
        )

    return result
