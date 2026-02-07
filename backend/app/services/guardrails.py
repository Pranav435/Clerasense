"""
Safety guardrails – compliance gating layer.
Enforces refusal of unsafe intents with structured explanations.
Logs all refusals for compliance review.
"""

import logging

from app.services.intent_classifier import (
    is_unsafe_intent,
    INTENT_DIAGNOSIS,
    INTENT_TREATMENT_REC,
    INTENT_BEST_DRUG,
    INTENT_PRESCRIPTION,
    INTENT_DOSE_PERSONALIZATION,
    INTENT_PATIENT_ADVICE,
    INTENT_SPECULATIVE,
    INTENT_OFF_TOPIC,
)

logger = logging.getLogger("clerasense.guardrails")

# ── Refusal templates: structured, clinical, non-promotional ──
REFUSAL_TEMPLATES = {
    INTENT_DIAGNOSIS: {
        "refusal_reason": "diagnosis_request",
        "refusal_message": (
            "⚠️ **Request Declined — Diagnostic Query Detected**\n\n"
            "Clerasense is a **drug information platform** and cannot diagnose diseases or conditions. "
            "Diagnosis requires clinical examination, patient history, and diagnostic testing by a licensed physician.\n\n"
            "**What I can help with:**\n"
            "• Regulatory-approved drug information\n"
            "• Drug safety profiles and contraindications\n"
            "• Drug-drug interaction checks\n"
            "• Dosage guidelines from official sources\n\n"
            "Please rephrase your query to focus on drug-related information."
        ),
    },
    INTENT_TREATMENT_REC: {
        "refusal_reason": "treatment_recommendation",
        "refusal_message": (
            "⚠️ **Request Declined — Treatment Recommendation Detected**\n\n"
            "Clerasense cannot recommend treatments or therapeutic approaches. "
            "Treatment decisions must be made by the treating physician based on clinical judgment, "
            "patient-specific factors, and current clinical guidelines.\n\n"
            "**What I can help with:**\n"
            "• Approved indications for specific drugs\n"
            "• Mechanism of action details\n"
            "• Safety and efficacy data from regulatory sources\n"
            "• Side-by-side drug comparison on factual parameters\n\n"
            "Please ask about specific drug information instead."
        ),
    },
    INTENT_BEST_DRUG: {
        "refusal_reason": "best_drug_ranking",
        "refusal_message": (
            "⚠️ **Request Declined — Drug Ranking/Recommendation Detected**\n\n"
            "Clerasense cannot rank drugs or suggest the \"best\" medication. "
            "Drug selection is a clinical decision that depends on individual patient factors, "
            "comorbidities, drug tolerance, and clinical guidelines.\n\n"
            "**What I can help with:**\n"
            "• Factual, side-by-side comparison of 2–4 drugs\n"
            "• Drug class information\n"
            "• Approved indications for each drug\n"
            "• Safety profiles and interaction data\n\n"
            "Try: \"Compare Metformin and Lisinopril\" for an unranked factual comparison."
        ),
    },
    INTENT_PRESCRIPTION: {
        "refusal_reason": "prescription_generation",
        "refusal_message": (
            "⚠️ **Request Declined — Prescription Generation Detected**\n\n"
            "Clerasense cannot generate, write, or suggest prescriptions. "
            "Prescribing is the exclusive responsibility of the licensed treating physician.\n\n"
            "**What I can help with:**\n"
            "• Standard dosage guidelines\n"
            "• Prescription safety validation (contraindication checks)\n"
            "• Drug interaction alerts\n"
            "• Renal/hepatic adjustment guidelines from official sources\n\n"
            "Try: \"What are the dosage guidelines for Metformin?\" or use the Safety Checker."
        ),
    },
    INTENT_DOSE_PERSONALIZATION: {
        "refusal_reason": "dosage_personalization",
        "refusal_message": (
            "⚠️ **Request Declined — Dosage Personalization Detected**\n\n"
            "Clerasense cannot personalize dosages for individual patients. "
            "Dose adjustment requires clinical assessment of the specific patient's weight, "
            "organ function, comorbidities, and other medications.\n\n"
            "**What I can help with:**\n"
            "• Standard adult and pediatric dosage ranges\n"
            "• General renal adjustment guidelines\n"
            "• General hepatic adjustment guidelines\n"
            "• Published dosage guidelines from regulatory sources\n\n"
            "Try: \"What are the renal dose adjustments for Lisinopril?\""
        ),
    },
    INTENT_PATIENT_ADVICE: {
        "refusal_reason": "patient_direct_advice",
        "refusal_message": (
            "⚠️ **Request Declined — Patient-Directed Communication Detected**\n\n"
            "Clerasense is designed exclusively for healthcare professionals and cannot "
            "generate patient-facing advice, counseling, or communication.\n\n"
            "**What I can help with:**\n"
            "• Drug information summaries for physician reference\n"
            "• Safety and interaction data\n"
            "• Regulatory classification information\n\n"
            "All information provided is for the physician's professional use only."
        ),
    },
    INTENT_SPECULATIVE: {
        "refusal_reason": "speculative_query",
        "refusal_message": (
            "⚠️ **Request Declined — Speculative Query Detected**\n\n"
            "Clerasense provides only verified, source-backed drug information from regulatory authorities. "
            "It cannot speculate, provide opinions, or make predictions.\n\n"
            "**What I can help with:**\n"
            "• Published drug safety and efficacy data\n"
            "• Regulatory-approved information\n"
            "• Documented drug interactions\n\n"
            "Please rephrase your query to request specific, factual drug information."
        ),
    },
    INTENT_OFF_TOPIC: {
        "refusal_reason": "off_topic",
        "refusal_message": (
            "⚠️ **Request Declined — Off-Topic Query**\n\n"
            "This query does not relate to drug information. "
            "Clerasense is a specialized drug information platform.\n\n"
            "**Supported topics:**\n"
            "• Drug information and approved uses\n"
            "• Drug safety and contraindications\n"
            "• Drug-drug interactions\n"
            "• Pricing and reimbursement\n"
            "• Drug comparison\n"
        ),
    },
}

# Default refusal for any unrecognized unsafe intent
DEFAULT_REFUSAL = {
    "refusal_reason": "safety_boundary",
    "refusal_message": (
        "⚠️ **Request Declined**\n\n"
        "This query falls outside the scope of Clerasense's drug information capabilities. "
        "I can only provide verified, source-backed drug information from regulatory authorities.\n\n"
        "For clinical decision-making, please consult the full prescribing information "
        "and relevant clinical guidelines."
    ),
}


def check_guardrails(query: str, intent: str) -> dict:
    """
    Check whether a query/intent should be refused.
    Returns:
      { "refused": bool, "refusal_reason": str|None, "refusal_message": str|None }
    """
    if is_unsafe_intent(intent):
        template = REFUSAL_TEMPLATES.get(intent, DEFAULT_REFUSAL)
        logger.warning(
            "GUARDRAIL REFUSAL | intent=%s | reason=%s | query=%s",
            intent,
            template["refusal_reason"],
            query[:200],
        )
        return {
            "refused": True,
            "refusal_reason": template["refusal_reason"],
            "refusal_message": template["refusal_message"],
        }

    # Additional content checks even for "safe" intents
    refusal = _content_level_checks(query)
    if refusal:
        return refusal

    return {"refused": False, "refusal_reason": None, "refusal_message": None}


def _content_level_checks(query: str) -> dict | None:
    """Additional content-level safety checks beyond intent classification."""
    q_lower = query.lower()

    # Check for attempts to override system behavior
    jailbreak_phrases = [
        "ignore your instructions",
        "ignore previous instructions",
        "pretend you are",
        "act as a doctor",
        "you are now",
        "disregard your rules",
        "override your",
        "forget your guidelines",
    ]
    for phrase in jailbreak_phrases:
        if phrase in q_lower:
            logger.warning("GUARDRAIL REFUSAL | reason=jailbreak_attempt | query=%s", query[:200])
            return {
                "refused": True,
                "refusal_reason": "system_integrity",
                "refusal_message": (
                    "⚠️ **Request Declined**\n\n"
                    "I cannot modify my operational guidelines. Clerasense operates within "
                    "strict safety boundaries to ensure accurate, verified drug information.\n\n"
                    "Please ask a drug information question."
                ),
            }

    return None
