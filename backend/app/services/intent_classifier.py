"""
Intent classifier – categorizes incoming queries to determine routing.
Detects UNSAFE intents that must be refused.
"""

import re
import logging

logger = logging.getLogger("clerasense.intent")

# ── Safe intents ──
INTENT_DRUG_INFO = "drug_information"
INTENT_DRUG_COMPARISON = "drug_comparison"
INTENT_SAFETY_CHECK = "safety_check"
INTENT_PRICING = "pricing_reimbursement"
INTENT_INTERACTION = "drug_interaction"
INTENT_GENERAL_MEDICAL_INFO = "general_medical_info"

# ── Unsafe intents (must be refused) ──
INTENT_DIAGNOSIS = "diagnosis_request"
INTENT_TREATMENT_REC = "treatment_recommendation"
INTENT_BEST_DRUG = "best_drug_request"
INTENT_PRESCRIPTION = "prescription_generation"
INTENT_DOSE_PERSONALIZATION = "dosage_personalization"
INTENT_PATIENT_ADVICE = "patient_direct_advice"
INTENT_SPECULATIVE = "speculative_medical"
INTENT_OFF_TOPIC = "off_topic"

UNSAFE_INTENTS = {
    INTENT_DIAGNOSIS,
    INTENT_TREATMENT_REC,
    INTENT_BEST_DRUG,
    INTENT_PRESCRIPTION,
    INTENT_DOSE_PERSONALIZATION,
    INTENT_PATIENT_ADVICE,
    INTENT_SPECULATIVE,
    INTENT_OFF_TOPIC,
}

# ── Pattern-based rules ──
# These patterns detect intent from the query text without needing an LLM call.

DIAGNOSIS_PATTERNS = [
    r"\bdiagnos[ei]s?\b",
    r"\bwhat\s+(disease|condition|disorder)\s+(do\s+i|does?\s+(the\s+)?patient)\b",
    r"\bwhat('s|s)\s+wrong\s+with\b",
    r"\bidentify\s+the\s+(disease|condition)\b",
    r"\bcould\s+(this|it)\s+be\b.*\b(disease|syndrome|disorder)\b",
    r"\bpatient\s+has\s+(symptoms?)\b.*\bwhat\b",
]

TREATMENT_REC_PATTERNS = [
    r"\bwhat\s+should\s+(i|we|the\s+doctor)\s+(prescribe|treat|give|recommend)\b",
    r"\bbest\s+(treatment|therapy|approach)\b",
    r"\bhow\s+(should|to)\s+treat\b",
    r"\brecommend\s+(a\s+)?(treatment|therapy|medication|drug)\b",
    r"\bwhich\s+(treatment|therapy)\s+(is|would\s+be)\b",
    r"\btreatment\s+plan\b",
]

BEST_DRUG_PATTERNS = [
    r"\bbest\s+(drug|medicine|medication)\b",
    r"\bwhich\s+(drug|medicine)\s+(is|would\s+be)\s+(best|better|superior|preferred)\b",
    r"\bmost\s+effective\s+(drug|medicine|medication)\b",
    r"\brecommend\s+(a\s+)?(drug|medicine)\b",
    r"\bshould\s+(i|we)\s+(choose|pick|select|use)\b",
    r"\btop\s+(drug|medicine|choice)\b",
]

PRESCRIPTION_PATTERNS = [
    r"\b(write|generate|create|make)\s+(a\s+)?prescription\b",
    r"\bprescription\s+for\b",
    r"\bprescribe\s+\w+\s+for\b",
    r"\brx\s+for\b",
]

DOSE_PERSONAL_PATTERNS = [
    r"\bwhat\s+dose\s+(should|for)\s+(this|my|the)\s+patient\b",
    r"\bhow\s+much\s+should\s+(this|my)\s+patient\s+take\b",
    r"\badjust\s+(the\s+)?dose\s+for\s+(this|my)\b",
    r"\bpersonali[sz]e\s+(the\s+)?dos(age|e)\b",
    r"\bfor\s+(a\s+)?\d+\s*(kg|lb|year|yo)\b.*\b(dose|dosage)\b",
]

PATIENT_ADVICE_PATTERNS = [
    r"\btell\s+(the\s+)?patient\b",
    r"\badvise\s+(the\s+)?patient\b",
    r"\bwhat\s+should\s+(the\s+)?patient\s+do\b",
    r"\bpatient\s+should\b",
    r"\byou\s+should\s+take\b",
]

SPECULATIVE_PATTERNS = [
    r"\bdo\s+you\s+think\b",
    r"\bwhat\s+would\s+happen\s+if\b.*\bspeculat\b",
    r"\bin\s+your\s+opinion\b",
    r"\bpredict\s+the\s+outcome\b",
]

# Safe intent patterns
COMPARISON_PATTERNS = [
    r"\bcompar[ei]\b",
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\bdifference\s+between\b",
    r"\b(how\s+does?|does?)\s+\w+\s+(differ|compare)\b",
]

PRICING_PATTERNS = [
    r"\b(cost|price|pricing|expensive|cheap|afford)\b",
    r"\b(generic|brand)\s+(available|alternative)\b",
    r"\b(reimburs|coverage|insur|medicare|medicaid)\b",
    r"\bhow\s+much\s+(does|is)\b",
]

INTERACTION_PATTERNS = [
    r"\binteract(ion)?s?\b",
    r"\b(take|use|combine)\s+\w+\s+(with|and|together)\b",
    r"\bcontraindicated\s+with\b",
    r"\b(safe|okay|ok)\s+to\s+(take|use|combine)\b.*\bwith\b",
]

SAFETY_PATTERNS = [
    r"\b(safe|safety)\b",
    r"\bside\s+effect\b",
    r"\bwarning\b",
    r"\bcontraindication\b",
    r"\bblack\s+box\b",
    r"\bpregnancy\b",
    r"\blactation\b",
    r"\badverse\b",
]


def classify_intent(query: str) -> str:
    """
    Classify the intent of a doctor's query.
    Returns one of the INTENT_* constants.
    Priority: unsafe intents checked first.
    """
    q = query.lower().strip()

    # ── Check unsafe intents first (order matters) ──
    if _matches(q, PRESCRIPTION_PATTERNS):
        return INTENT_PRESCRIPTION
    if _matches(q, DIAGNOSIS_PATTERNS):
        return INTENT_DIAGNOSIS
    if _matches(q, DOSE_PERSONAL_PATTERNS):
        return INTENT_DOSE_PERSONALIZATION
    if _matches(q, BEST_DRUG_PATTERNS):
        return INTENT_BEST_DRUG
    if _matches(q, TREATMENT_REC_PATTERNS):
        return INTENT_TREATMENT_REC
    if _matches(q, PATIENT_ADVICE_PATTERNS):
        return INTENT_PATIENT_ADVICE
    if _matches(q, SPECULATIVE_PATTERNS):
        return INTENT_SPECULATIVE

    # ── Safe intents ──
    if _matches(q, COMPARISON_PATTERNS):
        return INTENT_DRUG_COMPARISON
    if _matches(q, PRICING_PATTERNS):
        return INTENT_PRICING
    if _matches(q, INTERACTION_PATTERNS):
        return INTENT_INTERACTION
    if _matches(q, SAFETY_PATTERNS):
        return INTENT_SAFETY_CHECK

    # Default: treat as general drug information query
    return INTENT_DRUG_INFO


def is_unsafe_intent(intent: str) -> bool:
    return intent in UNSAFE_INTENTS


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)
