"""
Retrieval service – semantic search over drug embeddings.
Enforces the retrieval-before-LLM rule:
  No retrieval results → no LLM answer → explicit "Not available" message.
"""

import logging
from app.database import db
from app.models.models import Drug, Embedding
from app.services.embedding_service import generate_embedding, cosine_similarity

logger = logging.getLogger("clerasense.retrieval")

# Minimum similarity threshold – below this, data is considered not found.
SIMILARITY_THRESHOLD = 0.25
MAX_RESULTS = 5


def retrieve_drugs(query: str) -> list[dict]:
    """
    Perform semantic retrieval against cached drug embeddings.
    Returns a ranked list of drug dicts with similarity scores.
    Falls back to keyword search if no embeddings are available.
    """
    # Try semantic retrieval first
    results = _semantic_search(query)
    if results:
        return results

    # Fallback: keyword search
    return _keyword_search(query)


def _semantic_search(query: str) -> list[dict]:
    """Embed query and compare against cached drug embeddings."""
    try:
        query_vec = generate_embedding(query)
    except Exception as exc:
        logger.warning("Embedding generation failed, falling back to keyword: %s", exc)
        return []

    if not query_vec:
        return []

    all_embeddings = Embedding.query.filter_by(entity_type="drug", field_name="full_profile").all()
    if not all_embeddings:
        logger.info("No drug embeddings found in database. Run indexing first.")
        return []

    scored = []
    for emb in all_embeddings:
        sim = cosine_similarity(query_vec, emb.embedding)
        if sim >= SIMILARITY_THRESHOLD:
            scored.append((emb.entity_id, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:MAX_RESULTS]

    results = []
    for drug_id, score in top:
        drug = db.session.get(Drug, drug_id)
        if drug:
            d = drug.to_dict(include_details=True)
            d["relevance_score"] = round(score, 4)
            results.append(d)

    return results


def _keyword_search(query: str) -> list[dict]:
    """Simple keyword-based fallback search."""
    words = query.lower().split()
    candidates = set()

    for word in words:
        if len(word) < 3:
            continue
        drugs = Drug.query.filter(
            db.or_(
                Drug.generic_name.ilike(f"%{word}%"),
                Drug.drug_class.ilike(f"%{word}%"),
                Drug.mechanism_of_action.ilike(f"%{word}%"),
            )
        ).all()
        for d in drugs:
            candidates.add(d.id)

    results = []
    for drug_id in list(candidates)[:MAX_RESULTS]:
        drug = db.session.get(Drug, drug_id)
        if drug:
            d = drug.to_dict(include_details=True)
            d["relevance_score"] = 0.5  # Keyword match placeholder
            results.append(d)

    return results
