"""
Central drug lookup service – single source of truth for all modules.

Every module (chat, comparison, safety, pricing) MUST use this service
to retrieve drug data, instead of querying the DB directly. This ensures:

  1. Consistent data access across all features.
  2. On-demand ingestion: if a drug isn't in the DB, it's automatically
     fetched from public APIs, verified, and inserted before returning.
  3. All data is verified and source-backed regardless of which module
     requests it.

Lookup flow:
  DB check → (if missing) on-demand fetch from OpenFDA/DailyMed/RxNorm →
  cross-source verification → DB insert → embedding generation → return Drug
"""

import concurrent.futures
import logging
from typing import Optional

from flask import current_app

from app.database import db
from app.models.models import Drug

logger = logging.getLogger("clerasense.lookup")


def lookup_drug(name: str) -> Optional[Drug]:
    """
    Look up a drug by generic name.
    If not in the DB, triggers on-demand ingestion from public APIs.

    Returns:
        Drug ORM object (with all relations loaded) or None.
    """
    name = name.strip()
    if not name:
        return None

    # 1. Try exact match (case-insensitive)
    drug = Drug.query.filter(Drug.generic_name.ilike(name)).first()
    if drug:
        return drug

    # 2. Try partial match (e.g. user typed "metformin hcl" but DB has "Metformin")
    drug = Drug.query.filter(Drug.generic_name.ilike(f"%{name}%")).first()
    if drug:
        return drug

    # 3. Try matching against brand names
    # Use an in-memory scan because ARRAY .any() is PostgreSQL-specific
    # and does not work with SQLite or other backends.
    all_drugs = Drug.query.all()
    for d in all_drugs:
        if any(b.lower() == name.lower() for b in (d.brand_names or [])):
            drug = d
            break

    if drug:
        return drug

    # 4. Not in DB — trigger on-demand ingestion
    logger.info("Drug '%s' not in DB, attempting on-demand ingestion...", name)
    drug = _on_demand_ingest(name)
    return drug


def lookup_drugs(names: list[str]) -> tuple[list[Drug], list[str]]:
    """
    Look up multiple drugs by name — with parallel on-demand ingestion.

    Phase 1: Batch check which drugs are already in the DB (fast).
    Phase 2: Ingest all missing drugs in parallel threads.
    Phase 3: Reload results from the main DB session.

    Returns (found_drugs, not_found_names).
    """
    if not names:
        return [], []

    clean_names = [n.strip() for n in names if n.strip()]
    if not clean_names:
        return [], []

    # ── Phase 1: fast DB scan ──────────────────────────────────────
    found_map: dict[str, Drug] = {}            # clean_name → Drug
    missing: list[str] = []

    for name in clean_names:
        drug = Drug.query.filter(Drug.generic_name.ilike(name)).first()
        if not drug:
            drug = Drug.query.filter(Drug.generic_name.ilike(f"%{name}%")).first()
        if drug:
            found_map[name] = drug
            continue

        # brand-name fallback
        matched = False
        for d in Drug.query.all():
            if any(b.lower() == name.lower() for b in (d.brand_names or [])):
                found_map[name] = d
                matched = True
                break
        if not matched:
            missing.append(name)

    # ── Phase 2: parallel on-demand ingestion for missing drugs ────
    if missing:
        app = current_app._get_current_object()

        def _ingest_in_context(drug_name: str):
            """Run ingestion inside its own app context so each thread
            gets a fresh scoped DB session."""
            with app.app_context():
                return drug_name, _on_demand_ingest(drug_name)

        workers = min(len(missing), 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_ingest_in_context, n) for n in missing]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    name, drug = fut.result()
                    if drug:
                        found_map[name] = drug
                except Exception as exc:
                    logger.error("Parallel ingestion error: %s", exc)

    # ── Phase 3: reload in the *current* session to avoid detached objects
    drug_ids = [d.id for d in found_map.values()]
    if drug_ids:
        reloaded = {d.id: d for d in
                    Drug.query.filter(Drug.id.in_(drug_ids)).all()}
    else:
        reloaded = {}

    # preserve original order
    found: list[Drug] = []
    not_found: list[str] = []
    seen_ids: set[int] = set()
    for name in clean_names:
        drug = found_map.get(name)
        if drug and drug.id in reloaded and drug.id not in seen_ids:
            found.append(reloaded[drug.id])
            seen_ids.add(drug.id)
        elif not drug:
            not_found.append(name)

    return found, not_found


def search_drugs(query: str, limit: int = 10) -> list[Drug]:
    """
    Search for drugs matching a query string.
    Checks DB first, then tries external sources for discovery.
    """
    query = query.strip().lower()
    if not query:
        return []

    # DB keyword search
    results = Drug.query.filter(
        db.or_(
            Drug.generic_name.ilike(f"%{query}%"),
            Drug.drug_class.ilike(f"%{query}%"),
            Drug.mechanism_of_action.ilike(f"%{query}%"),
        )
    ).limit(limit).all()

    if results:
        return results

    # If nothing in DB, try discovering from external sources
    try:
        from app.services.drug_sources.openfda_source import OpenFDASource
        source = OpenFDASource()
        external_names = source.search_drugs(query, limit=5)
        for name in external_names:
            drug = lookup_drug(name)
            if drug:
                results.append(drug)
                if len(results) >= limit:
                    break
    except Exception as exc:
        logger.warning("External drug search failed: %s", exc)

    return results


def _on_demand_ingest(name: str) -> Optional[Drug]:
    """
    Fetch drug from public APIs, verify, insert, and return.
    This is the on-demand version of the background ingestion pipeline.
    """
    try:
        from app.services.drug_ingestion_service import ingest_single_drug

        result = ingest_single_drug(name)
        status = result.get("status")

        if status == "ingested":
            # Freshly ingested — fetch from DB
            drug = Drug.query.filter(Drug.generic_name.ilike(name.strip())).first()
            if drug:
                logger.info("On-demand ingestion succeeded for '%s'", name)
                return drug

        if status == "skipped":
            # Was already in DB (race condition) — just return it
            return Drug.query.filter(Drug.generic_name.ilike(name.strip())).first()

        logger.info("On-demand ingestion for '%s' ended with status: %s", name, status)
        return None

    except Exception as exc:
        logger.error("On-demand ingestion failed for '%s': %s", name, exc)
        return None
