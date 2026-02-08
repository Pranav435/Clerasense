"""
Prescription verification service.
Takes OCR'd prescription text and verifies it against the drug database
using AI analysis and verified drug safety data.

This is an INFORMATION tool — NOT a clinical approval system.
"""

import json
import logging
from openai import OpenAI

from app.config import Config
from app.services.drug_lookup_service import lookup_drugs

logger = logging.getLogger("clerasense.prescription")

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


# ── Prompt: extract structured data from OCR text ──────────────────────────

EXTRACTION_PROMPT = """You are a medical prescription text parser. Extract structured information from the following prescription text obtained via OCR.

Return a JSON object with exactly this structure:
{
    "medications": [
        {
            "drug_name": "generic name of the drug (use generic name if possible)",
            "dosage": "dosage if mentioned (e.g. '500mg')",
            "frequency": "frequency if mentioned (e.g. 'twice daily', 'BID')",
            "route": "route if mentioned (e.g. 'oral', 'IV')",
            "duration": "duration if mentioned (e.g. '7 days')",
            "quantity": "quantity if mentioned"
        }
    ],
    "patient_info": {
        "name": "patient name if visible",
        "age": "patient age if visible",
        "gender": "patient gender if visible",
        "weight": "patient weight if visible"
    },
    "diagnosis": "diagnosis, symptoms, or condition if mentioned",
    "prescriber": "prescribing doctor name if visible",
    "date": "prescription date if visible",
    "additional_instructions": "any other instructions or notes"
}

RULES:
- If information is not available, use null for that field.
- Only extract what is clearly present in the text. Do NOT infer or guess.
- For drug names, try to identify the generic/active ingredient name.
- OCR text may contain errors — use context to correct obvious typos in drug names.
- Common OCR errors in prescriptions: 0/O confusion, l/1 confusion, rn/m confusion.

Prescription text:
"""


# ── Prompt: comprehensive verification ─────────────────────────────────────

VERIFICATION_PROMPT = """You are Clerasense, a prescription verification assistant for licensed physicians.

ROLE: Cross-reference prescriptions with the verified drug database information provided below.
You are NOT a prescriber. You provide INFORMATION only.

CRITICAL RULES:
1. ONLY state facts that come from the "Drug database information" section below. Do NOT fabricate or hallucinate drug facts.
2. Every factual claim MUST include a "source" field citing the specific database source it came from (authority, document title, year from the "source" objects in the data).
3. If information is NOT in the database, say "Not available in verified database" — do NOT guess.
4. Keep each field SHORT — 1-2 sentences max. Doctors need to scan this quickly, not read essays.
5. Use clinical terminology. Be precise, not verbose.
6. For dosage assessment, compare ONLY against the database's adult_dosage field.

Return a JSON object with exactly this structure:
{{
    "overall_assessment": "VERIFIED" or "VERIFIED WITH CONCERNS" or "REQUIRES REVIEW",
    "assessment_summary": "One concise sentence.",
    "medication_analysis": [
        {{
            "drug_name": "...",
            "found_in_database": true/false,
            "drug_class": "from database or null",
            "prescribed_dosage": "what was prescribed (short)",
            "dosage_verdict": {{
                "status": "APPROPRIATE" or "HIGH" or "LOW" or "UNVERIFIABLE",
                "standard_range": "dosage range from database adult_dosage field",
                "note": "one sentence if needed",
                "source": "authority — document_title (year)"
            }},
            "indication_verdict": {{
                "status": "APPROPRIATE" or "NOT INDICATED" or "UNVERIFIABLE",
                "approved_uses": "approved indications from database",
                "note": "one sentence on match/mismatch with stated diagnosis",
                "source": "authority — document_title (year)"
            }},
            "black_box_warning": "text from database or null",
            "contraindications_summary": "1-2 sentence summary from database or null",
            "pregnancy_risk": "from database or null",
            "key_warnings": [
                {{
                    "text": "concise warning text",
                    "source": "authority — document_title (year)"
                }}
            ],
            "monitoring": [
                {{
                    "test": "test/lab name",
                    "timing": "before starting / periodic / etc.",
                    "reason": "one sentence"
                }}
            ],
            "dosage_instructions": "frequency, timing, food interactions — brief",
            "renal_adjustment": "from database or null",
            "hepatic_adjustment": "from database or null"
        }}
    ],
    "interaction_alerts": [
        {{
            "drugs": ["drug A", "drug B"],
            "severity": "severity level",
            "description": "one sentence",
            "clinical_action": "what to do about it",
            "source": "authority — document_title (year)"
        }}
    ],
    "required_scans_and_tests": [
        {{
            "test_name": "name",
            "reason": "one sentence",
            "timing": "when",
            "related_drug": "which drug"
        }}
    ],
    "missing_information": ["short items"],
    "recommendations": ["short actionable items"]
}}

Prescription data:
{prescription_data}

Drug database information (from verified regulatory sources — FDA, DailyMed, NIH):
{drug_info}

Database interaction records:
{interaction_info}"""


DISCLAIMER = (
    "DISCLAIMER: This prescription verification provides information from verified "
    "regulatory sources and AI analysis. It does NOT constitute a clinical review, "
    "approval, or recommendation. The prescribing physician is solely responsible "
    "for all clinical decisions. Always refer to the full prescribing information."
)


def extract_prescription_data(ocr_text: str) -> dict:
    """Use OpenAI to extract structured data from OCR'd prescription text."""
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a prescription text parser. Return valid JSON only.",
                },
                {"role": "user", "content": EXTRACTION_PROMPT + ocr_text},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error("Prescription extraction failed: %s", e)
        return {"error": str(e), "medications": []}


def _build_drug_context(drugs_found: list) -> dict:
    """Gather comprehensive drug info from DB for verification."""
    drug_info = {}
    for drug in drugs_found:
        d = drug.to_dict(include_details=True)
        drug_info[drug.generic_name] = {
            "drug_class": d.get("drug_class"),
            "mechanism_of_action": d.get("mechanism_of_action"),
            "indications": d.get("indications", []),
            "safety_warnings": d.get("safety_warnings", []),
            "dosage_guidelines": d.get("dosage_guidelines", []),
        }
    return drug_info


def _collect_interaction_alerts(drugs_found: list) -> list:
    """Check for drug-drug interactions among the prescribed medications."""
    interaction_alerts = []
    drug_names_lower = {d.generic_name.lower() for d in drugs_found}
    seen = set()
    for drug in drugs_found:
        for ix in drug.interactions:
            if ix.interacting_drug.lower() in drug_names_lower:
                pair = tuple(sorted([drug.generic_name.lower(), ix.interacting_drug.lower()]))
                if pair in seen:
                    continue
                seen.add(pair)
                interaction_alerts.append({
                    "drug_a": drug.generic_name,
                    "drug_b": ix.interacting_drug,
                    "severity": ix.severity,
                    "description": ix.description,
                    "source": ix.source.to_dict() if ix.source else None,
                })
    return interaction_alerts


def _collect_safety_warnings(drugs_found: list) -> list:
    """Gather all safety warnings from the DB for the prescribed drugs."""
    warnings = []
    for drug in drugs_found:
        for sw in drug.safety_warnings:
            warnings.append({
                "drug": drug.generic_name,
                "contraindications": sw.contraindications,
                "black_box_warnings": sw.black_box_warnings,
                "pregnancy_risk": sw.pregnancy_risk,
                "lactation_risk": sw.lactation_risk,
                "adverse_event_count": sw.adverse_event_count,
                "adverse_event_serious_count": sw.adverse_event_serious_count,
                "top_adverse_reactions": (
                    json.loads(sw.top_adverse_reactions)
                    if sw.top_adverse_reactions else []
                ),
                "source": sw.source.to_dict() if sw.source else None,
            })
    return warnings


def _collect_dosage_guidelines(drugs_found: list) -> dict:
    """Gather dosage guidelines from the DB for the prescribed drugs."""
    guidelines = {}
    for drug in drugs_found:
        entries = []
        for dg in drug.dosage_guidelines:
            entries.append({
                "adult_dosage": dg.adult_dosage,
                "pediatric_dosage": dg.pediatric_dosage,
                "renal_adjustment": dg.renal_adjustment,
                "hepatic_adjustment": dg.hepatic_adjustment,
                "source": dg.source.to_dict() if dg.source else None,
            })
        if entries:
            guidelines[drug.generic_name] = entries
    return guidelines


def _run_ai_verification(extracted: dict, drug_info: dict, interaction_alerts: list) -> dict:
    """Run the AI-powered comprehensive verification analysis."""
    try:
        client = _get_client()
        prompt = VERIFICATION_PROMPT.format(
            prescription_data=json.dumps(extracted, indent=2),
            drug_info=json.dumps(drug_info, indent=2, default=str),
            interaction_info=json.dumps(interaction_alerts, indent=2, default=str),
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a prescription verification assistant. "
                        "Return valid JSON only. Be thorough and precise."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error("AI verification failed: %s", e)
        return {"error": f"AI analysis unavailable: {str(e)}"}


def verify_prescription(ocr_text: str) -> dict:
    """
    Full prescription verification pipeline.
    1. Extract structured data from OCR text (via AI).
    2. Look up drugs in the verified database.
    3. Gather safety warnings, interactions, dosage guidelines.
    4. Run AI-powered comprehensive verification.
    5. Return combined result.
    """
    # Step 1: Extract structured data from OCR text
    extracted = extract_prescription_data(ocr_text)
    if extracted.get("error"):
        return {"error": f"Could not parse prescription: {extracted['error']}"}

    medications = extracted.get("medications", [])
    if not medications:
        return {
            "error": "No medications could be identified in the prescription text.",
            "extracted_data": extracted,
        }

    # Step 2: Look up drugs in database
    drug_names = [m["drug_name"] for m in medications if m.get("drug_name")]
    drugs_found, not_found = lookup_drugs(drug_names)

    # Step 3: Gather comprehensive drug info from DB
    drug_info = _build_drug_context(drugs_found)
    interaction_alerts = _collect_interaction_alerts(drugs_found)
    safety_warnings = _collect_safety_warnings(drugs_found)
    dosage_guidelines = _collect_dosage_guidelines(drugs_found)

    # Step 4: AI-powered comprehensive verification
    ai_analysis = _run_ai_verification(extracted, drug_info, interaction_alerts)

    # Step 5: Combine everything into the response
    return {
        "extracted_data": extracted,
        "drugs_found": [d.generic_name for d in drugs_found],
        "drugs_not_found": not_found,
        "safety_warnings": safety_warnings,
        "interaction_alerts": interaction_alerts,
        "dosage_guidelines": dosage_guidelines,
        "ai_analysis": ai_analysis,
        "disclaimer": DISCLAIMER,
    }
