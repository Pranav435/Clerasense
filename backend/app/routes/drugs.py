"""
Drug information routes – CRUD + search endpoints.
All responses include source citations.
"""

from flask import Blueprint, request, jsonify
from app.database import db
from app.models.models import Drug

drugs_bp = Blueprint("drugs", __name__)


@drugs_bp.route("/", methods=["GET"])
def list_drugs():
    """List all drugs with optional search by name or class."""
    q = request.args.get("q", "").strip().lower()
    drug_class = request.args.get("class", "").strip().lower()

    query = Drug.query
    if q:
        query = query.filter(
            db.or_(
                Drug.generic_name.ilike(f"%{q}%"),
                Drug.brand_names.any(q),
            )
        )
    if drug_class:
        query = query.filter(Drug.drug_class.ilike(f"%{drug_class}%"))

    drugs = query.order_by(Drug.generic_name).all()
    return jsonify({"drugs": [d.to_dict() for d in drugs]}), 200


@drugs_bp.route("/<int:drug_id>", methods=["GET"])
def get_drug(drug_id):
    """Return full drug profile with all related data and sources."""
    drug = db.session.get(Drug, drug_id)
    if not drug:
        return jsonify({"error": "Drug not found."}), 404
    return jsonify({"drug": drug.to_dict(include_details=True)}), 200


@drugs_bp.route("/by-name/<string:name>", methods=["GET"])
def get_drug_by_name(name):
    """Lookup drug by generic name (case-insensitive)."""
    drug = Drug.query.filter(Drug.generic_name.ilike(name)).first()
    if not drug:
        return jsonify({"error": f"Drug '{name}' not found in verified database."}), 404
    return jsonify({"drug": drug.to_dict(include_details=True)}), 200
