"""
Drug ingestion service – orchestrates fetching from public APIs,
cross-source verification, and database insertion.

Flow:
  1. Discover drug names from OpenFDA catalogue.
  2. For each drug not yet in our DB, fetch data from all sources.
  3. Run cross-source verification.
  4. Insert verified data into the normalized schema.
  5. Trigger embedding generation for new drugs.
"""

import concurrent.futures
import logging
from datetime import datetime
from typing import Optional

from app.database import db
from app.models.models import (
    Drug, Source, Indication, DosageGuideline, SafetyWarning,
    DrugInteraction, Pricing, Reimbursement, Embedding, IngestionLog,
)
from app.services.drug_sources.base_source import NormalizedDrugData
from app.services.drug_sources.openfda_source import OpenFDASource, get_fda_drug_list
from app.services.drug_sources.dailymed_source import DailyMedSource
from app.services.drug_sources.rxnorm_source import RxNormSource
from app.services.drug_sources.nadac_source import NADACSource
from app.services.verification_service import verify_drug_data, VerificationResult
from app.services.embedding_service import build_drug_text, generate_embedding
from app.config import Config

logger = logging.getLogger("clerasense.ingestion")

# Instantiate source adapters
_openfda = OpenFDASource()
_dailymed = DailyMedSource()
_rxnorm = RxNormSource()
_nadac = NADACSource()


def _log_ingestion(
    drug_name: str,
    source_api: str,
    status: str,
    confidence: float = 0.0,
    sources: list[str] = None,
    conflicts: list[str] = None,
    notes: str = "",
) -> None:
    """Write an ingestion event to the ingestion_log table."""
    try:
        log = IngestionLog(
            drug_name=drug_name,
            source_api=source_api,
            status=status,
            confidence=confidence,
            sources_used=sources or [],
            conflicts="; ".join(conflicts) if conflicts else None,
            details=notes,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning("Failed to write ingestion log: %s", exc)


def _get_or_create_source(
    authority: str,
    document_title: str,
    url: str = "",
    year: int = None,
    effective_date: str = "",
    data_retrieved_at: str = "",
) -> Source:
    """Find existing source or create a new one."""
    existing = Source.query.filter_by(
        authority=authority,
        document_title=document_title,
    ).first()
    if existing:
        # Update fields if we have newer info
        if effective_date and not existing.effective_date:
            existing.effective_date = effective_date
        if data_retrieved_at:
            try:
                existing.data_retrieved_at = datetime.fromisoformat(data_retrieved_at)
            except (ValueError, TypeError):
                pass
        if url and (not existing.url or existing.url != url):
            existing.url = url
        return existing

    source = Source(
        authority=authority,
        document_title=document_title,
        publication_year=year or datetime.now().year,
        url=url,
        effective_date=effective_date or None,
        data_retrieved_at=datetime.fromisoformat(data_retrieved_at) if data_retrieved_at else datetime.utcnow(),
    )
    db.session.add(source)
    db.session.flush()  # Get source_id without committing
    return source


def _drug_exists(generic_name: str) -> bool:
    """Check if a drug already exists in the database."""
    return Drug.query.filter(
        Drug.generic_name.ilike(generic_name.strip())
    ).first() is not None


def _insert_verified_drug(data: NormalizedDrugData, verification: VerificationResult) -> Optional[Drug]:
    """
    Insert a verified drug and all related records into the database.
    Returns the new Drug object or None on failure.
    """
    try:
        # Create the primary source
        primary_source = _get_or_create_source(
            authority=data.source_authority,
            document_title=data.source_document_title,
            url=data.source_url,
            year=data.source_year,
            effective_date=data.effective_date,
            data_retrieved_at=data.data_retrieved_at,
        )

        # Create additional sources for each API that contributed
        additional_sources = {}
        for src_name in verification.sources_used:
            if src_name != data.source_authority:
                alt_url = verification.all_source_urls.get(src_name, "")
                alt_source = _get_or_create_source(
                    authority=src_name,
                    document_title=f"{src_name} – {data.generic_name}",
                    url=alt_url,
                    year=data.source_year,
                )
                additional_sources[src_name] = alt_source

        # Insert drug
        drug = Drug(
            generic_name=data.generic_name.strip().title(),
            brand_names=data.brand_names or [],
            drug_class=data.drug_class or "",
            mechanism_of_action=data.mechanism_of_action or "",
            source_id=primary_source.source_id,
        )
        db.session.add(drug)
        db.session.flush()

        # Indications
        for indication_text in (data.indications or []):
            if indication_text and indication_text.strip():
                ind = Indication(
                    drug_id=drug.id,
                    approved_use=indication_text.strip(),
                    source_id=primary_source.source_id,
                )
                db.session.add(ind)

        # Dosage
        if data.adult_dosage or data.pediatric_dosage:
            dosage = DosageGuideline(
                drug_id=drug.id,
                adult_dosage=data.adult_dosage or None,
                pediatric_dosage=data.pediatric_dosage or None,
                renal_adjustment=data.renal_adjustment or None,
                hepatic_adjustment=data.hepatic_adjustment or None,
                source_id=primary_source.source_id,
            )
            db.session.add(dosage)

        # Safety warnings — always create a record so the safety module has data
        import json
        top_reactions_json = json.dumps(data.top_adverse_reactions) if data.top_adverse_reactions else None
        safety = SafetyWarning(
            drug_id=drug.id,
            contraindications=data.contraindications or "No specific contraindications listed in FDA labeling.",
            black_box_warnings=data.black_box_warnings or None,
            pregnancy_risk=data.pregnancy_risk or "Consult prescribing information for pregnancy safety data.",
            lactation_risk=data.lactation_risk or "Consult prescribing information for lactation safety data.",
            adverse_event_count=data.adverse_event_count,
            adverse_event_serious_count=data.adverse_event_serious_count,
            top_adverse_reactions=top_reactions_json,
            source_id=primary_source.source_id,
        )
        db.session.add(safety)

        # Drug interactions
        for ix in (data.interactions or []):
            interaction = DrugInteraction(
                drug_id=drug.id,
                interacting_drug=ix.get("interacting_drug", "Unknown"),
                severity=ix.get("severity", "moderate"),
                description=ix.get("description", ""),
                source_id=primary_source.source_id,
            )
            db.session.add(interaction)

        # Pricing — prefer NADAC real data over estimates
        approximate_cost = data.approximate_cost or "Contact pharmacy for current pricing"
        generic_available = data.generic_available if data.generic_available is not None else False

        # Determine pricing source type
        pricing_source_type = "NADAC" if data.nadac_per_unit else "estimate"

        # If we have NADAC data, create a NADAC source for pricing
        if data.nadac_per_unit:
            nadac_url = f"https://data.medicaid.gov/dataset/dfa2ab14-06c2-457a-9e36-5cb6d80f8d93?conditions[0][property]=ndc_description&conditions[0][value]={data.generic_name.upper()}&conditions[0][operator]=contains"
            nadac_src = _get_or_create_source(
                authority="CMS",
                document_title=f"NADAC Weekly Price – {data.generic_name}",
                url=nadac_url,
                year=data.source_year,
                data_retrieved_at=data.data_retrieved_at,
            )
            pricing_source_id = nadac_src.source_id
        else:
            pricing_source_id = primary_source.source_id

        price = Pricing(
            drug_id=drug.id,
            approximate_cost=approximate_cost,
            generic_available=generic_available,
            nadac_per_unit=data.nadac_per_unit,
            nadac_ndc=data.nadac_ndc or None,
            nadac_effective_date=data.nadac_effective_date or None,
            nadac_package_description=data.nadac_package_description or None,
            pricing_source=pricing_source_type,
            source_id=pricing_source_id,
        )
        db.session.add(price)

        db.session.commit()
        logger.info("Inserted drug '%s' (id=%s) with %.1f%% confidence",
                     drug.generic_name, drug.id, verification.confidence * 100)
        return drug

    except Exception as exc:
        db.session.rollback()
        logger.error("Failed to insert drug '%s': %s", data.generic_name, exc)
        return None


def _generate_embedding_for_drug(drug: Drug) -> None:
    """Generate and store embedding for a newly inserted drug."""
    try:
        # Check if already exists
        existing = Embedding.query.filter_by(
            entity_type="drug", entity_id=drug.id, field_name="full_profile"
        ).first()
        if existing:
            return

        text = build_drug_text(drug)
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
            db.session.commit()
            logger.info("Generated embedding for drug '%s'", drug.generic_name)
    except Exception as exc:
        db.session.rollback()
        logger.warning("Embedding generation failed for '%s': %s", drug.generic_name, exc)


def ingest_single_drug(drug_name: str, delay_scale: float = 0.2) -> dict:
    """
    Full ingestion pipeline for a single drug:
      1. Check if already in DB
      2. Fetch from all sources (in parallel)
      3. Cross-verify
      4. Insert if verified
      5. Generate embedding

    Args:
        delay_scale: Multiplier for API rate-limit sleep.
            0.2 = fast on-demand (~3-5x speedup), 1.0 = safe batch mode.

    Returns a status dict.
    """
    drug_name = drug_name.strip().title()

    if _drug_exists(drug_name):
        return {"drug": drug_name, "status": "skipped", "reason": "Already in database"}

    logger.info("Ingesting drug: %s", drug_name)

    # Create source instances with the requested delay scale.
    # Each adapter now embeds interaction extraction in fetch_drug_data(),
    # eliminating redundant HTTP calls (DailyMed double-fetch, OpenFDA label re-fetch).
    fda = OpenFDASource(delay_scale=delay_scale)
    dm = DailyMedSource(delay_scale=delay_scale)
    rx = RxNormSource(delay_scale=delay_scale)
    nadac = NADACSource(delay_scale=delay_scale)

    # Fetch from all 4 independent APIs in parallel
    source_results: list[NormalizedDrugData] = []
    fetchers = {
        "OpenFDA": lambda: fda.fetch_drug_data(drug_name),
        "DailyMed": lambda: dm.fetch_drug_data(drug_name),
        "RxNorm": lambda: rx.fetch_drug_data(drug_name),
        "NADAC": lambda: nadac.fetch_drug_data(drug_name),
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_name = {
            executor.submit(fn): name for name, fn in fetchers.items()
        }
        for future in concurrent.futures.as_completed(future_to_name):
            src_name = future_to_name[future]
            try:
                data = future.result()
                if data:
                    source_results.append(data)
                    logger.debug("%s returned data for '%s'", src_name, drug_name)
            except Exception as exc:
                logger.warning("%s fetch failed for '%s': %s", src_name, drug_name, exc)

    if not source_results:
        _log_ingestion(drug_name, "discovery", "not_found", notes="No sources returned data")
        return {"drug": drug_name, "status": "not_found", "reason": "No sources returned data"}

    # Cross-source verification
    verification = verify_drug_data(drug_name, source_results)

    if not verification.verified or not verification.merged_data:
        _log_ingestion(drug_name, "verification", "unverified",
                       notes="; ".join(verification.notes),
                       sources=verification.sources_used)
        return {
            "drug": drug_name,
            "status": "unverified",
            "reason": "; ".join(verification.notes),
            "sources_tried": len(source_results),
        }

    # Insert into database
    drug = _insert_verified_drug(verification.merged_data, verification)
    if not drug:
        _log_ingestion(drug_name, "insertion", "failed", notes="Database insert failed",
                       sources=verification.sources_used)
        return {"drug": drug_name, "status": "insert_failed", "reason": "Database insert failed"}

    # Generate embedding
    _generate_embedding_for_drug(drug)

    _log_ingestion(drug_name, "ingestion", "ingested",
                   confidence=verification.confidence,
                   sources=verification.sources_used,
                   conflicts=verification.conflicts)

    return {
        "drug": drug_name,
        "status": "ingested",
        "confidence": verification.confidence,
        "sources": verification.sources_used,
        "conflicts": verification.conflicts,
        "drug_id": drug.id,
    }


def discover_and_ingest(batch_size: int = 20, max_batches: int = 5) -> dict:
    """
    Discover new drugs from the OpenFDA catalogue and ingest them.
    Processes in batches to be resource-friendly.

    Returns summary statistics.
    """
    stats = {
        "discovered": 0,
        "ingested": 0,
        "skipped": 0,
        "failed": 0,
        "unverified": 0,
        "details": [],
    }

    for batch_idx in range(max_batches):
        skip = batch_idx * batch_size
        drug_names = get_fda_drug_list(skip=skip, limit=batch_size)

        if not drug_names:
            logger.info("No more drugs to discover at offset %d", skip)
            break

        stats["discovered"] += len(drug_names)

        for name in drug_names:
            result = ingest_single_drug(name, delay_scale=1.0)
            status = result.get("status", "unknown")

            if status == "ingested":
                stats["ingested"] += 1
            elif status == "skipped":
                stats["skipped"] += 1
            elif status == "unverified":
                stats["unverified"] += 1
            else:
                stats["failed"] += 1

            stats["details"].append(result)

        logger.info(
            "Batch %d/%d complete: %d ingested, %d skipped",
            batch_idx + 1, max_batches, stats["ingested"], stats["skipped"],
        )

    return stats


def update_existing_drugs() -> dict:
    """
    Re-verify and update existing drugs with latest data from public sources.
    Only updates fields that have new/better information.
    """
    stats = {"updated": 0, "unchanged": 0, "errors": 0}

    drugs = Drug.query.all()
    for drug in drugs:
        try:
            name = drug.generic_name

            # Fetch fresh data from sources
            source_results = []
            try:
                fda_data = _openfda.fetch_drug_data(name)
                if fda_data:
                    source_results.append(fda_data)
            except Exception:
                pass
            try:
                dm_data = _dailymed.fetch_drug_data(name)
                if dm_data:
                    source_results.append(dm_data)
            except Exception:
                pass

            if not source_results:
                stats["unchanged"] += 1
                continue

            verification = verify_drug_data(name, source_results)
            if not verification.verified or not verification.merged_data:
                stats["unchanged"] += 1
                continue

            merged = verification.merged_data
            updated = False

            # Update fields if new data is more detailed
            if merged.mechanism_of_action and len(merged.mechanism_of_action) > len(drug.mechanism_of_action or ""):
                drug.mechanism_of_action = merged.mechanism_of_action
                updated = True

            if merged.brand_names:
                existing_brands = set(b.lower() for b in (drug.brand_names or []))
                new_brands = [b for b in merged.brand_names if b.lower() not in existing_brands]
                if new_brands:
                    drug.brand_names = list(set((drug.brand_names or []) + new_brands))
                    updated = True

            if merged.drug_class and not drug.drug_class:
                drug.drug_class = merged.drug_class
                updated = True

            if updated:
                db.session.commit()
                stats["updated"] += 1
                # Regenerate embedding
                existing_emb = Embedding.query.filter_by(
                    entity_type="drug", entity_id=drug.id, field_name="full_profile"
                ).first()
                if existing_emb:
                    db.session.delete(existing_emb)
                    db.session.commit()
                _generate_embedding_for_drug(drug)
            else:
                stats["unchanged"] += 1

        except Exception as exc:
            db.session.rollback()
            logger.error("Update failed for drug '%s': %s", drug.generic_name, exc)
            stats["errors"] += 1

    return stats
