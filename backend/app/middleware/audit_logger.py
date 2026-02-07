"""
Audit logger – after-request hook that writes every API interaction
to the audit_log table. Also tracks refusals for compliance review.
"""

import json
import logging
from flask import request, g
from app.database import db
from app.models.models import AuditLog

logger = logging.getLogger("clerasense.audit")


def audit_after_request(response):
    """Log every API request/response pair for compliance auditing."""
    if not request.path.startswith("/api/"):
        return response

    # Skip health checks from filling the log
    if request.path == "/api/health":
        return response

    try:
        doctor = getattr(g, "current_doctor", None)
        doctor_id = doctor.id if doctor else None

        # Capture request body (truncated for safety)
        req_body = None
        if request.is_json:
            try:
                body = request.get_json(silent=True) or {}
                # Redact sensitive fields
                safe_body = {k: v for k, v in body.items() if k not in ("password", "token")}
                req_body = json.dumps(safe_body)[:2000]
            except Exception:
                req_body = "<unreadable>"

        # Check if response indicates a refusal
        was_refused = False
        refusal_reason = None
        resp_summary = None
        if response.is_json:
            try:
                resp_data = response.get_json(silent=True) or {}
                was_refused = resp_data.get("refused", False)
                refusal_reason = resp_data.get("refusal_reason")
                resp_summary = json.dumps(resp_data)[:2000]
            except Exception:
                resp_summary = "<unreadable>"

        entry = AuditLog(
            doctor_id=doctor_id,
            endpoint=request.path,
            method=request.method,
            request_body=req_body,
            response_summary=resp_summary,
            was_refused=was_refused,
            refusal_reason=refusal_reason,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        logger.warning("Audit logging failed: %s", exc)
        db.session.rollback()

    return response
