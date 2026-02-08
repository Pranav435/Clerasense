"""
Drug information routes – CRUD + search endpoints.
All responses include source citations.
Uses the central drug_lookup_service for consistent data access.
"""

from difflib import SequenceMatcher
from flask import Blueprint, request, jsonify
from app.database import db
from app.models.models import Drug
from app.services.drug_lookup_service import lookup_drug, search_drugs as central_search
from app.services.brand_service import get_brands_for_drug
from app.services.market_brand_service import get_market_brands_for_drug, get_country_name

drugs_bp = Blueprint("drugs", __name__)


@drugs_bp.route("/", methods=["GET"])
def list_drugs():
    """List all drugs with optional search by name or class."""
    q = request.args.get("q", "").strip().lower()
    drug_class = request.args.get("class", "").strip().lower()

    if q:
        # Use central search which can also discover drugs from external APIs
        drugs = central_search(q)
        if drug_class:
            drugs = [d for d in drugs if d.drug_class and drug_class in d.drug_class.lower()]
    elif drug_class:
        drugs = Drug.query.filter(Drug.drug_class.ilike(f"%{drug_class}%")).order_by(Drug.generic_name).all()
    else:
        drugs = Drug.query.order_by(Drug.generic_name).all()
    return jsonify({"drugs": [d.to_dict() for d in drugs]}), 200


@drugs_bp.route("/<int:drug_id>", methods=["GET"])
def get_drug(drug_id):
    """Return full drug profile with all related data and sources."""
    drug = db.session.get(Drug, drug_id)
    if not drug:
        return jsonify({"error": "Drug not found."}), 404
    return jsonify({"drug": drug.to_dict(include_details=True)}), 200


@drugs_bp.route("/autocomplete", methods=["GET"])
def autocomplete_drugs():
    """Return up to 8 drug names matching a prefix (lightweight, no details).
    Falls back to fuzzy matching when no prefix/substring matches found."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"suggestions": []}), 200

    # First try exact prefix / substring match (fast, uses DB index)
    matches = (
        Drug.query
        .filter(Drug.generic_name.ilike(f"%{q}%"))
        .order_by(
            db.case(
                (Drug.generic_name.ilike(f"{q}%"), 0),
                else_=1,
            ),
            Drug.generic_name,
        )
        .limit(8)
        .all()
    )

    # If no prefix/substring matches, fall back to fuzzy matching
    is_fuzzy = False
    if not matches:
        matches = _fuzzy_match_drugs(q, limit=8, cutoff=0.45)
        is_fuzzy = bool(matches)

    return jsonify({
        "suggestions": [
            {"name": d.generic_name, "drug_class": d.drug_class or ""}
            for d in matches
        ],
        "fuzzy": is_fuzzy,
    }), 200


@drugs_bp.route("/suggest", methods=["GET"])
def suggest_drugs():
    """Return fuzzy-matched drug name suggestions for misspelled queries."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"suggestions": []}), 200
    matches = _fuzzy_match_drugs(q, limit=6, cutoff=0.40)
    return jsonify({
        "suggestions": [
            {"name": d.generic_name, "drug_class": d.drug_class or ""}
            for d in matches
        ]
    }), 200


def _fuzzy_match_drugs(query, limit=6, cutoff=0.40):
    """Find drugs whose names are similar to *query* using SequenceMatcher.

    Scores each drug name against the query and returns the top matches
    above the cutoff threshold, sorted best-first.
    """
    all_drugs = Drug.query.all()
    q_lower = query.lower()

    scored = []
    for drug in all_drugs:
        name_lower = drug.generic_name.lower()
        # Compute similarity ratio
        ratio = SequenceMatcher(None, q_lower, name_lower).ratio()

        # Boost score if the query is a prefix of the drug name or vice-versa
        if name_lower.startswith(q_lower) or q_lower.startswith(name_lower):
            ratio = max(ratio, 0.85)
        # Boost if query appears as a substring
        elif q_lower in name_lower or name_lower in q_lower:
            ratio = max(ratio, 0.75)

        # Also check against brand names
        brand_names = drug.brand_names or []
        for bn in brand_names:
            bn_lower = bn.lower()
            bn_ratio = SequenceMatcher(None, q_lower, bn_lower).ratio()
            if bn_lower.startswith(q_lower) or q_lower.startswith(bn_lower):
                bn_ratio = max(bn_ratio, 0.85)
            elif q_lower in bn_lower or bn_lower in q_lower:
                bn_ratio = max(bn_ratio, 0.75)
            ratio = max(ratio, bn_ratio)

        if ratio >= cutoff:
            scored.append((ratio, drug))

    scored.sort(key=lambda x: -x[0])
    return [drug for _, drug in scored[:limit]]


@drugs_bp.route("/by-name/<string:name>", methods=["GET"])
def get_drug_by_name(name):
    """
    Lookup drug by generic name (case-insensitive).
    Triggers on-demand ingestion if not in DB.
    """
    drug = lookup_drug(name)
    if not drug:
        return jsonify({"error": f"Drug '{name}' not found in verified sources."}), 404
    return jsonify({"drug": drug.to_dict(include_details=True)}), 200


@drugs_bp.route("/<int:drug_id>/brands", methods=["GET"])
def get_drug_brands(drug_id):
    """
    Return all brand products for a drug.
    Accepts optional ?country=XX query parameter (ISO 3166-1 alpha-2).
    Fetches on-demand from verified sources if not yet cached.
    """
    drug = db.session.get(Drug, drug_id)
    if not drug:
        return jsonify({"error": "Drug not found."}), 404

    country = request.args.get("country", "US").strip().upper()[:5]
    brands = get_market_brands_for_drug(drug, country)

    return jsonify({
        "brands": brands,
        "generic_name": drug.generic_name,
        "country": country,
        "country_name": get_country_name(country),
    }), 200


@drugs_bp.route("/<int:drug_id>/brands/compare", methods=["POST"])
def compare_brands(drug_id):
    """
    Compare selected brand products side-by-side.
    Expects JSON body: { "brand_ids": [1, 2, 3] }
    """
    drug = db.session.get(Drug, drug_id)
    if not drug:
        return jsonify({"error": "Drug not found."}), 404

    body = request.get_json(silent=True) or {}
    brand_ids = body.get("brand_ids", [])
    if len(brand_ids) < 2:
        return jsonify({"error": "Need at least 2 brands to compare."}), 400
    if len(brand_ids) > 6:
        return jsonify({"error": "Maximum 6 brands can be compared at once."}), 400

    from app.models.models import BrandProduct
    brands = BrandProduct.query.filter(
        BrandProduct.id.in_(brand_ids),
        BrandProduct.drug_id == drug_id,
    ).all()

    if len(brands) < 2:
        return jsonify({"error": "Not enough valid brands found."}), 404

    return jsonify({
        "generic_name": drug.generic_name,
        "brands": [b.to_dict() for b in brands],
    }), 200
