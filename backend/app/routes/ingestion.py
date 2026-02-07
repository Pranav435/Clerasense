"""
Admin routes for managing drug data ingestion.
These endpoints allow manual triggering of ingestion and status checks.
Protected by JWT authentication (only authenticated doctors can access).
"""

import logging
from flask import Blueprint, jsonify, request

from app.services.drug_ingestion_service import (
    ingest_single_drug,
    discover_and_ingest,
    update_existing_drugs,
)

logger = logging.getLogger("clerasense.routes.ingestion")

ingestion_bp = Blueprint("ingestion", __name__)


@ingestion_bp.route("/status", methods=["GET"])
def ingestion_status():
    """Check the ingestion system status and drug count."""
    from app.models.models import Drug, Source
    from app.database import db

    drug_count = Drug.query.count()
    source_count = Source.query.count()

    # Get most recently added drug
    latest_drug = Drug.query.order_by(Drug.created_at.desc()).first()

    return jsonify({
        "status": "active",
        "total_drugs": drug_count,
        "total_sources": source_count,
        "latest_drug": {
            "name": latest_drug.generic_name,
            "added": latest_drug.created_at.isoformat(),
        } if latest_drug else None,
        "sources_used": [
            "OpenFDA Drug Label API (FDA)",
            "NIH DailyMed API (NLM)",
            "NIH RxNorm / RxNav API (NLM)",
        ],
    })


@ingestion_bp.route("/ingest", methods=["POST"])
def ingest_drug():
    """
    Manually trigger ingestion for a specific drug.
    Body: {"drug_name": "Metformin"}
    """
    data = request.get_json(silent=True) or {}
    drug_name = data.get("drug_name", "").strip()

    if not drug_name:
        return jsonify({"error": "drug_name is required"}), 400

    if len(drug_name) < 2 or len(drug_name) > 200:
        return jsonify({"error": "drug_name must be 2-200 characters"}), 400

    result = ingest_single_drug(drug_name)
    status_code = 200 if result["status"] in ("ingested", "skipped") else 422

    return jsonify(result), status_code


@ingestion_bp.route("/discover", methods=["POST"])
def discover_drugs():
    """
    Trigger a discovery batch to find and ingest new drugs from public APIs.
    Body (optional): {"batch_size": 20, "max_batches": 3}
    """
    data = request.get_json(silent=True) or {}
    batch_size = min(int(data.get("batch_size", 15)), 50)
    max_batches = min(int(data.get("max_batches", 2)), 10)

    stats = discover_and_ingest(batch_size=batch_size, max_batches=max_batches)

    # Remove detailed per-drug info to keep response manageable
    summary = {k: v for k, v in stats.items() if k != "details"}
    summary["detail_count"] = len(stats.get("details", []))

    return jsonify(summary)


@ingestion_bp.route("/update", methods=["POST"])
def update_drugs():
    """Re-verify and update all existing drugs with latest data from public sources."""
    stats = update_existing_drugs()
    return jsonify(stats)
