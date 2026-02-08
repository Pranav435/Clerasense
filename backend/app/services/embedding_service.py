"""
Embedding service – generates and caches embeddings for drug data fields.
Uses OpenAI's embedding API. API key loaded from environment only.
"""

import logging
import numpy as np
from openai import OpenAI

from app.config import Config
from app.database import db
from app.models.models import Embedding, Drug

logger = logging.getLogger("clerasense.embeddings")

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for a text string."""
    if not text or not text.strip():
        return []
    client = _get_client()
    resp = client.embeddings.create(
        input=text.strip(),
        model=Config.EMBEDDING_MODEL_NAME,
    )
    return resp.data[0].embedding


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def build_drug_text(drug: Drug) -> str:
    """Concatenate all drug fields into a single searchable text block."""
    parts = [
        f"Drug: {drug.generic_name}",
        f"Brand names: {', '.join(drug.brand_names or [])}",
        f"Class: {drug.drug_class or ''}",
        f"Mechanism: {drug.mechanism_of_action or ''}",
    ]
    for ind in drug.indications:
        parts.append(f"Indication: {ind.approved_use}")
    for dg in drug.dosage_guidelines:
        parts.append(f"Adult dosage: {dg.adult_dosage or ''}")
        parts.append(f"Pediatric dosage: {dg.pediatric_dosage or ''}")
        parts.append(f"Renal adjustment: {dg.renal_adjustment or ''}")
        parts.append(f"Hepatic adjustment: {dg.hepatic_adjustment or ''}")
        parts.append(f"Overdose information: {dg.overdose_info or ''}")
        parts.append(f"Underdose / missed dose: {dg.underdose_info or ''}")
        parts.append(f"Administration details: {dg.administration_info or ''}")
    for sw in drug.safety_warnings:
        parts.append(f"Contraindications: {sw.contraindications or ''}")
        parts.append(f"Black box warnings: {sw.black_box_warnings or ''}")
        parts.append(f"Pregnancy risk: {sw.pregnancy_risk or ''}")
        parts.append(f"Lactation risk: {sw.lactation_risk or ''}")
    for ix in drug.interactions:
        parts.append(f"Interaction with {ix.interacting_drug}: {ix.severity} – {ix.description}")

    return "\n".join(p for p in parts if p.strip())


def index_all_drugs():
    """Generate and cache embeddings for all drugs in the database."""
    drugs = Drug.query.all()
    count = 0
    for drug in drugs:
        text = build_drug_text(drug)
        existing = Embedding.query.filter_by(
            entity_type="drug", entity_id=drug.id, field_name="full_profile"
        ).first()
        if existing:
            continue  # Skip already indexed
        try:
            vec = generate_embedding(text)
            if vec:
                emb = Embedding(
                    entity_type="drug",
                    entity_id=drug.id,
                    field_name="full_profile",
                    embedding=vec,
                    model_name=Config.EMBEDDING_MODEL_NAME,
                )
                db.session.add(emb)
                count += 1
        except Exception as exc:
            logger.warning("Failed to embed drug %s: %s", drug.generic_name, exc)

    db.session.commit()
    logger.info("Indexed %d drugs.", count)
    return count
