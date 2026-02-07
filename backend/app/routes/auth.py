"""
Authentication routes – doctor registration and login.
Returns JWT tokens for authenticated sessions.
"""

from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
import bcrypt
import jwt as pyjwt

from app.config import Config
from app.database import db
from app.models.models import Doctor

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new doctor account."""
    data = request.get_json(force=True)
    required = ["email", "password", "full_name", "license_number"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    if Doctor.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered."}), 409

    if Doctor.query.filter_by(license_number=data["license_number"]).first():
        return jsonify({"error": "License number already registered."}), 409

    pw_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()

    doctor = Doctor(
        email=data["email"],
        password_hash=pw_hash,
        full_name=data["full_name"],
        license_number=data["license_number"],
        specialization=data.get("specialization"),
    )
    db.session.add(doctor)
    db.session.commit()

    token = _issue_token(doctor)
    return jsonify({"token": token, "doctor": doctor.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate a doctor and return a JWT."""
    data = request.get_json(force=True)
    email = data.get("email", "")
    password = data.get("password", "")

    doctor = Doctor.query.filter_by(email=email).first()
    if not doctor or not bcrypt.checkpw(password.encode(), doctor.password_hash.encode()):
        return jsonify({"error": "Invalid email or password."}), 401

    if not doctor.is_active:
        return jsonify({"error": "Account deactivated. Contact administrator."}), 403

    token = _issue_token(doctor)
    return jsonify({"token": token, "doctor": doctor.to_dict()}), 200


def _issue_token(doctor: Doctor) -> str:
    payload = {
        "doctor_id": doctor.id,
        "email": doctor.email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")
