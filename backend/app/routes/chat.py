"""
Chat route – Drug Information Chat (RAG pipeline endpoint).
Enforces: retrieval-before-LLM, mandatory citations, safety gating.
"""

from flask import Blueprint, request, jsonify, g
from app.services.rag_service import generate_rag_response
from app.services.intent_classifier import classify_intent
from app.services.guardrails import check_guardrails

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/", methods=["POST"])
def drug_chat():
    """
    Natural-language drug information chat.
    Body: { "query": "What are the safety warnings for Metformin?" }
    """
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    conversation_history = data.get("conversation_history", [])

    if not query:
        return jsonify({"error": "Query cannot be empty."}), 400
    if len(query) > 1000:
        return jsonify({"error": "Query too long (max 1000 characters)."}), 400

    # Validate and trim conversation history (max 20 turns)
    if not isinstance(conversation_history, list):
        conversation_history = []
    conversation_history = conversation_history[-20:]

    # 1. Intent classification
    intent = classify_intent(query)

    # 2. Safety guardrail check
    guardrail_result = check_guardrails(query, intent)
    if guardrail_result["refused"]:
        doctor = getattr(g, "current_doctor", None)
        return jsonify({
            "refused": True,
            "refusal_reason": guardrail_result["refusal_reason"],
            "response": guardrail_result["refusal_message"],
            "intent_detected": intent,
            "sources": [],
        }), 200

    # 3. RAG pipeline: retrieve → context → LLM summarize → cite
    rag_result = generate_rag_response(query, intent, conversation_history=conversation_history)

    return jsonify({
        "refused": False,
        "response": rag_result["response"],
        "sections": rag_result.get("sections", {}),
        "sources": rag_result["sources"],
        "intent_detected": intent,
        "disclaimer": (
            "This information is sourced from verified regulatory authorities. "
            "It is not medical advice. The treating physician must independently "
            "verify all information before making clinical decisions."
        ),
    }), 200
