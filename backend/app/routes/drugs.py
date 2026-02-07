"""
Drug information routes – CRUD + search endpoints.
All responses include source citations.
Uses the central drug_lookup_service for consistent data access.
"""

from flask import Blueprint, request, jsonify
from app.database import db
from app.models.models import Drug
from app.services.drug_lookup_service import lookup_drug, search_drugs as central_search

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
    """Return up to 8 drug names matching a prefix (lightweight, no details)."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"suggestions": []}), 200
    matches = (
        Drug.query
        .filter(Drug.generic_name.ilike(f"%{q}%"))
        .order_by(
            # Prefer prefix matches first, then contains
            db.case(
                (Drug.generic_name.ilike(f"{q}%"), 0),
                else_=1,
            ),
            Drug.generic_name,
        )
        .limit(8)
        .all()
    )
    return jsonify({
        "suggestions": [
            {"name": d.generic_name, "drug_class": d.drug_class or ""}
            for d in matches
        ]
    }), 200


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
