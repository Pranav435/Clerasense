"""
Pricing & reimbursement routes.
Returns cost estimates, generic availability, and government scheme coverage.
Uses the central drug_lookup_service for consistent data access.
"""

from flask import Blueprint, request, jsonify
from app.services.drug_lookup_service import lookup_drug
from app.services.reimbursement_service import get_reimbursement_info, get_supported_countries

pricing_bp = Blueprint("pricing", __name__)

PRICING_DISCLAIMER = (
    "Prices shown are approximate estimates from publicly available sources. "
    "Actual costs may vary by pharmacy, region, insurance plan, and time of purchase. "
    "This information is for reference only and does not guarantee coverage or pricing."
)


@pricing_bp.route("/<string:drug_name>", methods=["GET"])
def get_pricing(drug_name):
    """
    Get pricing and reimbursement info for a drug by generic name.

    Query parameters:
        country  – ISO 3166-1 alpha-2 code (e.g. US, IN, GB).
                   Defaults to US. Controls which government reimbursement
                   schemes are returned.

    If the drug is not in the local database, it is automatically
    fetched from verified public APIs, cross-verified, and inserted
    before returning pricing data.
    """
    country = request.args.get("country", "US").upper().strip()

    drug = lookup_drug(drug_name)
    if not drug:
        return jsonify({"error": f"Drug '{drug_name}' not found in verified sources."}), 404

    pricing_data = [p.to_dict() for p in drug.pricing]

    # Country-specific reimbursement from curated schemes
    reimbursement_data = get_reimbursement_info(drug, country)

    return jsonify({
        "drug": drug.generic_name,
        "brand_names": drug.brand_names or [],
        "pricing": pricing_data,
        "reimbursement": reimbursement_data,
        "reimbursement_country": country,
        "generic_available": any(p.generic_available for p in drug.pricing),
        "disclaimer": PRICING_DISCLAIMER,
    }), 200


@pricing_bp.route("/reimbursement/countries", methods=["GET"])
def list_reimbursement_countries():
    """Return the list of countries with curated reimbursement data."""
    return jsonify({"countries": get_supported_countries()}), 200
