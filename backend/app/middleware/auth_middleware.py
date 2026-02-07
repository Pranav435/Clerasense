"""
Authentication middleware – JWT-based doctor-only access.
All /api/* routes (except /api/auth/* and /api/health) require a valid JWT.
"""

from functools import wraps
from flask import request, g, jsonify
import jwt as pyjwt

from app.config import Config
from app.database import db
from app.models.models import Doctor

# Routes that do not require authentication
PUBLIC_PREFIXES = ("/api/auth", "/api/health")


def jwt_required_middleware():
    """Before-request hook: validates JWT bearer token."""
    if request.method == "OPTIONS":
        return None

    path = request.path
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return None

    if not path.startswith("/api/"):
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid Authorization header."}), 401

    token = auth_header.split(" ", 1)[1]
    try:
        payload = pyjwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired."}), 401
    except pyjwt.InvalidTokenError:
        return jsonify({"error": "Invalid token."}), 401

    doctor = db.session.get(Doctor, payload.get("doctor_id"))
    if not doctor or not doctor.is_active:
        return jsonify({"error": "Doctor account not found or deactivated."}), 403

    g.current_doctor = doctor
    return None


def get_current_doctor() -> Doctor:
    """Convenience accessor for the authenticated doctor."""
    return getattr(g, "current_doctor", None)
