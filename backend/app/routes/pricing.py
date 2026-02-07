"""
Pricing & reimbursement routes.
Returns cost estimates, generic availability, and government scheme coverage.
"""

from flask import Blueprint, request, jsonify
from app.database import db
from app.models.models import Drug

pricing_bp = Blueprint("pricing", __name__)

PRICING_DISCLAIMER = (
    "Prices shown are approximate estimates from publicly available sources. "
    "Actual costs may vary by pharmacy, region, insurance plan, and time of purchase. "
    "This information is for reference only and does not guarantee coverage or pricing."
)


@pricing_bp.route("/<string:drug_name>", methods=["GET"])
def get_pricing(drug_name):
    """Get pricing and reimbursement info for a drug by generic name."""
    drug = Drug.query.filter(Drug.generic_name.ilike(drug_name.strip())).first()
    if not drug:
        return jsonify({"error": f"Drug '{drug_name}' not found in verified database."}), 404

    pricing_data = [p.to_dict() for p in drug.pricing]
    reimbursement_data = [r.to_dict() for r in drug.reimbursements]

    return jsonify({
        "drug": drug.generic_name,
        "brand_names": drug.brand_names or [],
        "pricing": pricing_data,
        "reimbursement": reimbursement_data,
        "generic_available": any(p.generic_available for p in drug.pricing),
        "disclaimer": PRICING_DISCLAIMER,
    }), 200
