"""
Drug comparison route – compare 2-4 drugs on fixed factual dimensions.
No ranking. No recommendations.
"""

from flask import Blueprint, request, jsonify
from app.database import db
from app.models.models import Drug

comparison_bp = Blueprint("comparison", __name__)


@comparison_bp.route("/", methods=["POST"])
def compare_drugs():
    """
    Compare 2–4 drugs on fixed factual dimensions.
    Body: { "drug_names": ["Metformin", "Lisinopril"] }
    """
    data = request.get_json(force=True)
    drug_names = data.get("drug_names", [])

    if not isinstance(drug_names, list) or len(drug_names) < 2:
        return jsonify({"error": "Provide at least 2 drug names for comparison."}), 400
    if len(drug_names) > 4:
        return jsonify({"error": "Comparison is limited to a maximum of 4 drugs."}), 400

    results = []
    not_found = []
    for name in drug_names:
        drug = Drug.query.filter(Drug.generic_name.ilike(name.strip())).first()
        if not drug:
            not_found.append(name)
            continue
        results.append(drug.to_dict(include_details=True))

    disclaimer = (
        "This comparison presents factual, source-backed information only. "
        "No ranking or recommendation is implied. Consult the full prescribing "
        "information for each drug before making clinical decisions."
    )

    response = {
        "comparison": results,
        "not_found": not_found,
        "disclaimer": disclaimer,
        "note": "All data sourced from regulatory authorities. See individual source objects for citations.",
    }
    return jsonify(response), 200
