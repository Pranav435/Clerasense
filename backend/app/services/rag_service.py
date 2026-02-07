"""
RAG (Retrieval-Augmented Generation) service.
Strict rules:
  1. Retrieve first — no retrieval means no LLM call.
  2. LLM only summarizes retrieved data.
  3. Every claim must cite its source.
  4. Missing data → explicit "Not available in verified sources." message.
  5. Neutral, clinical tone. No recommendations.
"""

import json
import logging
from openai import OpenAI

from app.config import Config
from app.services.retrieval_service import retrieve_drugs

logger = logging.getLogger("clerasense.rag")

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = """You are Clerasense, an AI-powered drug information assistant for licensed physicians.

ABSOLUTE RULES — you must never violate these:
1. You are an INFORMATION ASSISTANT only. You are NOT a doctor, NOT a diagnostician, NOT a prescriber.
2. You may ONLY present information from the RETRIEVED CONTEXT provided below. Do NOT use any other knowledge.
3. Every factual statement MUST cite its source using [Source: authority, document_title, year] format.
4. If information is not in the retrieved context, say: "This information is not available in verified sources."
5. NEVER diagnose, recommend treatments, suggest the "best drug", generate prescriptions, or personalize dosages.
6. NEVER address patients directly. Your audience is licensed physicians only.
7. NEVER use promotional, marketing, or persuasive language.
8. Use a neutral, clinical, factual tone.
9. If asked to do anything outside drug information (diagnosis, treatment recommendation, etc.), refuse with:
   "I can only provide verified drug information from regulatory sources. For clinical decision-making, please consult the full prescribing information and relevant clinical guidelines."

OUTPUT FORMAT:
Structure your response with these sections as applicable:
- **Approved Uses**: FDA/regulatory approved indications
- **Dosage Overview**: Standard dosing guidelines
- **Safety Warnings**: Contraindications, black box warnings
- **Drug Interactions**: Known interactions with severity
- **Regulatory Notes**: Pregnancy category, special populations
- **Sources**: List all cited sources

If the query doesn't relate to the retrieved drugs, state that clearly."""


def generate_rag_response(query: str, intent: str) -> dict:
    """
    Full RAG pipeline:
      1. Retrieve relevant drug data from DB
      2. If nothing found → return "not available" without calling LLM
      3. Build context from retrieved data
      4. Call LLM to summarize with citations
      5. Collect and return sources
    """
    # Step 1: Retrieve
    retrieved = retrieve_drugs(query)

    # Step 2: No retrieval → no answer (hard rule)
    if not retrieved:
        return {
            "response": (
                "The requested information is not available in our verified sources. "
                "Our database contains regulatory-approved drug information only. "
                "If you believe this drug should be included, please contact the Clerasense team."
            ),
            "sections": {},
            "sources": [],
        }

    # Step 3: Build context
    context_text = _build_context(retrieved)
    all_sources = _collect_sources(retrieved)

    # Step 4: Call LLM with strict system prompt + retrieved context
    try:
        client = _get_client()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"RETRIEVED CONTEXT (only use this data):\n\n{context_text}\n\n"
                    f"---\nDoctor's query: {query}\n\n"
                    "Provide a structured, source-cited response using ONLY the retrieved context above."
                ),
            },
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1,  # Low temperature for factual accuracy
            max_tokens=2000,
        )
        answer = response.choices[0].message.content
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        # Fallback: return structured data directly without LLM summarization
        answer = _format_fallback(retrieved)

    return {
        "response": answer,
        "sections": _extract_sections(answer),
        "sources": all_sources,
    }


def _build_context(retrieved: list[dict]) -> str:
    """Build a text context block from retrieved drug data for the LLM."""
    parts = []
    for drug in retrieved:
        block = [f"=== {drug['generic_name']} ({', '.join(drug.get('brand_names', []))}) ==="]
        block.append(f"Drug Class: {drug.get('drug_class', 'N/A')}")
        block.append(f"Mechanism: {drug.get('mechanism_of_action', 'N/A')}")

        if drug.get("source"):
            s = drug["source"]
            block.append(f"[Source: {s['authority']}, {s['document_title']}, {s.get('publication_year', '')}]")

        for ind in drug.get("indications", []):
            src = ind.get("source", {})
            cite = f"[Source: {src.get('authority','')}, {src.get('document_title','')}, {src.get('publication_year','')}]" if src else ""
            block.append(f"Approved Use: {ind['approved_use']} {cite}")

        for dg in drug.get("dosage_guidelines", []):
            src = dg.get("source", {})
            cite = f"[Source: {src.get('authority','')}, {src.get('document_title','')}, {src.get('publication_year','')}]" if src else ""
            block.append(f"Adult Dosage: {dg.get('adult_dosage', 'N/A')} {cite}")
            block.append(f"Pediatric Dosage: {dg.get('pediatric_dosage', 'N/A')}")
            block.append(f"Renal Adjustment: {dg.get('renal_adjustment', 'N/A')}")
            block.append(f"Hepatic Adjustment: {dg.get('hepatic_adjustment', 'N/A')}")

        for sw in drug.get("safety_warnings", []):
            src = sw.get("source", {})
            cite = f"[Source: {src.get('authority','')}, {src.get('document_title','')}, {src.get('publication_year','')}]" if src else ""
            block.append(f"Contraindications: {sw.get('contraindications', 'N/A')} {cite}")
            block.append(f"Black Box Warnings: {sw.get('black_box_warnings', 'N/A')}")
            block.append(f"Pregnancy Risk: {sw.get('pregnancy_risk', 'N/A')}")
            block.append(f"Lactation Risk: {sw.get('lactation_risk', 'N/A')}")

        for ix in drug.get("interactions", []):
            src = ix.get("source", {})
            cite = f"[Source: {src.get('authority','')}, {src.get('document_title','')}, {src.get('publication_year','')}]" if src else ""
            block.append(f"Interaction with {ix['interacting_drug']}: [{ix['severity']}] {ix['description']} {cite}")

        parts.append("\n".join(block))

    return "\n\n".join(parts)


def _collect_sources(retrieved: list[dict]) -> list[dict]:
    """Deduplicate and collect all sources from retrieved data."""
    seen = set()
    sources = []
    for drug in retrieved:
        all_src = [drug.get("source")]
        for section in ("indications", "dosage_guidelines", "safety_warnings", "interactions", "pricing", "reimbursements"):
            for item in drug.get(section, []):
                all_src.append(item.get("source"))

        for src in all_src:
            if src and src.get("source_id") and src["source_id"] not in seen:
                seen.add(src["source_id"])
                sources.append(src)

    return sources


def _extract_sections(text: str) -> dict:
    """Attempt to extract named sections from the LLM response."""
    sections = {}
    current_key = None
    current_lines = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("**") and stripped.endswith("**"):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = stripped.strip("*").strip(":").strip()
            current_lines = []
        elif stripped.startswith("## ") or stripped.startswith("### "):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def _format_fallback(retrieved: list[dict]) -> str:
    """Format retrieved data as plain text when LLM is unavailable."""
    parts = ["[LLM unavailable — showing raw retrieved data]\n"]
    for drug in retrieved:
        parts.append(f"**{drug['generic_name']}** ({', '.join(drug.get('brand_names', []))})")
        parts.append(f"Class: {drug.get('drug_class', 'N/A')}")
        parts.append(f"Mechanism: {drug.get('mechanism_of_action', 'N/A')}")

        for ind in drug.get("indications", []):
            parts.append(f"• Indication: {ind['approved_use']}")
        for sw in drug.get("safety_warnings", []):
            parts.append(f"• Contraindications: {sw.get('contraindications', 'N/A')}")
            parts.append(f"• Black Box: {sw.get('black_box_warnings', 'N/A')}")
        parts.append("")

    return "\n".join(parts)
