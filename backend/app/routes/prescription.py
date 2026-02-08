"""
Prescription verification route.
Accepts OCR'd prescription text and returns comprehensive verification results
including AI analysis, drug interactions, safety warnings, and dosage guidance.

This is an INFORMATION tool — NOT a clinical approval system.
"""

from flask import Blueprint, request, jsonify
from app.services.prescription_service import verify_prescription

prescription_bp = Blueprint("prescription", __name__)


@prescription_bp.route("/verify", methods=["POST"])
def verify():
    """
    Verify a prescription from OCR'd text.

    Body: {
        "ocr_text": "Full text extracted from prescription via OCR"
    }

    Returns comprehensive verification including:
    - Extracted prescription data (medications, patient info, diagnosis)
    - Drug database lookups (safety warnings, interactions, dosage)
    - AI-powered analysis (appropriateness, monitoring, recommendations)
    """
    data = request.get_json(force=True)
    ocr_text = data.get("ocr_text", "").strip()

    if not ocr_text:
        return jsonify({"error": "No prescription text provided."}), 400

    if len(ocr_text) > 15000:
        return jsonify({"error": "Prescription text too long (max 15,000 characters)."}), 400

    result = verify_prescription(ocr_text)

    if result.get("error") and "drugs_found" not in result:
        return jsonify(result), 422

    return jsonify(result), 200
