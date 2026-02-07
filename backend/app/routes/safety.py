"""
Prescription safety checker route.
Checks contraindications, drug-drug interactions, and safety warnings.
This is an information tool — NOT a prescription generator.
Uses the central drug_lookup_service for consistent data access.
"""

from flask import Blueprint, request, jsonify
from app.services.drug_lookup_service import lookup_drugs

safety_bp = Blueprint("safety", __name__)

SAFETY_DISCLAIMER = (
    "DISCLAIMER: This safety check provides information from verified regulatory sources only. "
    "It does NOT constitute a prescription review, clinical recommendation, or diagnostic output. "
    "The prescribing physician is solely responsible for all clinical decisions."
)


@safety_bp.route("/check", methods=["POST"])
def check_safety():
    """
    Check safety for a list of drugs with optional context flags.
    Body: {
        "drug_names": ["Metformin", "Lisinopril"],
        "context": { "pregnancy": true, "renal_impairment": true }
    }

    If a drug is not in the local database, it is automatically
    fetched from verified public APIs, cross-verified, and inserted
    before running safety checks.
    """
    data = request.get_json(force=True)
    drug_names = data.get("drug_names", [])
    context = data.get("context", {})

    if not drug_names:
        return jsonify({"error": "Provide at least one drug name."}), 400

    drugs_found, not_found = lookup_drugs(drug_names)

    # 1. Collect all warnings
    warnings = []
    for drug in drugs_found:
        for sw in drug.safety_warnings:
            entry = {
                "drug": drug.generic_name,
                "contraindications": sw.contraindications,
                "black_box_warnings": sw.black_box_warnings,
                "pregnancy_risk": sw.pregnancy_risk,
                "lactation_risk": sw.lactation_risk,
                "source": sw.source.to_dict() if sw.source else None,
            }
            warnings.append(entry)

    # 2. Check interactions between the provided drugs
    interaction_alerts = []
    drug_names_lower = [d.generic_name.lower() for d in drugs_found]
    for drug in drugs_found:
        for ix in drug.interactions:
            # Check if the interacting drug is in the provided list
            if ix.interacting_drug.lower() in drug_names_lower:
                interaction_alerts.append({
                    "drug_a": drug.generic_name,
                    "drug_b": ix.interacting_drug,
                    "severity": ix.severity,
                    "description": ix.description,
                    "source": ix.source.to_dict() if ix.source else None,
                })

    # 3. Context-aware alerts
    context_alerts = []
    if context.get("pregnancy"):
        for drug in drugs_found:
            for sw in drug.safety_warnings:
                if sw.pregnancy_risk and sw.pregnancy_risk.upper() in ("CATEGORY D", "CATEGORY X"):
                    context_alerts.append({
                        "drug": drug.generic_name,
                        "alert_type": "pregnancy",
                        "risk_category": sw.pregnancy_risk,
                        "detail": "This drug carries significant pregnancy risk per FDA classification.",
                        "source": sw.source.to_dict() if sw.source else None,
                    })

    if context.get("renal_impairment"):
        for drug in drugs_found:
            for dg in drug.dosage_guidelines:
                if dg.renal_adjustment and "contraindicated" in dg.renal_adjustment.lower():
                    context_alerts.append({
                        "drug": drug.generic_name,
                        "alert_type": "renal_impairment",
                        "detail": dg.renal_adjustment,
                        "source": dg.source.to_dict() if dg.source else None,
                    })

    if context.get("hepatic_impairment"):
        for drug in drugs_found:
            for dg in drug.dosage_guidelines:
                if dg.hepatic_adjustment and ("contraindicated" in dg.hepatic_adjustment.lower() or "avoid" in dg.hepatic_adjustment.lower()):
                    context_alerts.append({
                        "drug": drug.generic_name,
                        "alert_type": "hepatic_impairment",
                        "detail": dg.hepatic_adjustment,
                        "source": dg.source.to_dict() if dg.source else None,
                    })

    return jsonify({
        "safety_warnings": warnings,
        "interaction_alerts": interaction_alerts,
        "context_alerts": context_alerts,
        "drugs_not_found": not_found,
        "disclaimer": SAFETY_DISCLAIMER,
    }), 200
