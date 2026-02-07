"""
Background scheduler for continuous drug data ingestion.
Uses APScheduler to run periodic tasks within the Flask app context.

Jobs:
  1. discover_new_drugs   – every 6 hours, discover and ingest new drugs
  2. update_existing_drugs – every 24 hours, re-verify existing drug data
  3. reindex_embeddings    – every 12 hours, ensure all drugs have embeddings
"""

import logging
import atexit
from typing import Optional

from flask import Flask

logger = logging.getLogger("clerasense.scheduler")

_scheduler = None


def init_scheduler(app: Flask) -> None:
    """
    Initialize and start the background scheduler.
    Must be called after the Flask app is fully configured.
    """
    global _scheduler

    # Only run scheduler in the main process (not in reloader subprocess)
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.config.get("DEBUG"):
        # In debug mode, only start in the reloader's child process
        logger.info("Scheduler deferred to reloader child process.")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning(
            "APScheduler not installed. Background drug ingestion disabled. "
            "Install with: pip install apscheduler"
        )
        return

    _scheduler = BackgroundScheduler(daemon=True)

    # Job 1: Discover new drugs from public APIs
    _scheduler.add_job(
        func=_job_discover_drugs,
        trigger=IntervalTrigger(hours=6),
        id="discover_new_drugs",
        name="Discover and ingest new drugs from public APIs",
        replace_existing=True,
        kwargs={"app": app},
        misfire_grace_time=3600,
    )

    # Job 2: Update/re-verify existing drugs
    _scheduler.add_job(
        func=_job_update_drugs,
        trigger=IntervalTrigger(hours=24),
        id="update_existing_drugs",
        name="Re-verify and update existing drug data",
        replace_existing=True,
        kwargs={"app": app},
        misfire_grace_time=3600,
    )

    # Job 3: Re-index embeddings for any drugs missing them
    _scheduler.add_job(
        func=_job_reindex_embeddings,
        trigger=IntervalTrigger(hours=12),
        id="reindex_embeddings",
        name="Generate embeddings for unindexed drugs",
        replace_existing=True,
        kwargs={"app": app},
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info("Background scheduler started with 3 recurring jobs.")

    # Shut down cleanly on app exit
    atexit.register(lambda: _shutdown_scheduler())


def _shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler shut down.")


def _job_discover_drugs(app: Flask) -> None:
    """Scheduled job: discover and ingest new drugs."""
    with app.app_context():
        try:
            from app.services.drug_ingestion_service import discover_and_ingest
            logger.info("Starting scheduled drug discovery...")
            stats = discover_and_ingest(batch_size=15, max_batches=3)
            logger.info(
                "Drug discovery complete: discovered=%d, ingested=%d, skipped=%d, failed=%d",
                stats["discovered"], stats["ingested"], stats["skipped"], stats["failed"],
            )
        except Exception as exc:
            logger.error("Drug discovery job failed: %s", exc, exc_info=True)


def _job_update_drugs(app: Flask) -> None:
    """Scheduled job: update existing drug data."""
    with app.app_context():
        try:
            from app.services.drug_ingestion_service import update_existing_drugs
            logger.info("Starting scheduled drug data update...")
            stats = update_existing_drugs()
            logger.info(
                "Drug update complete: updated=%d, unchanged=%d, errors=%d",
                stats["updated"], stats["unchanged"], stats["errors"],
            )
        except Exception as exc:
            logger.error("Drug update job failed: %s", exc, exc_info=True)


def _job_reindex_embeddings(app: Flask) -> None:
    """Scheduled job: generate embeddings for drugs that don't have them."""
    with app.app_context():
        try:
            from app.services.embedding_service import index_all_drugs
            from app.database import db
            logger.info("Starting scheduled embedding re-index...")
            index_all_drugs()
            db.session.commit()
            logger.info("Embedding re-index complete.")
        except Exception as exc:
            logger.error("Embedding re-index job failed: %s", exc, exc_info=True)


def run_initial_ingestion(app: Flask) -> None:
    """
    Run an immediate ingestion pass on startup if the database has very few drugs.
    This bootstraps the system on first deployment.
    """
    with app.app_context():
        from app.models.models import Drug

        drug_count = Drug.query.count()
        if drug_count < 10:
            logger.info(
                "Database has only %d drugs. Running initial ingestion to bootstrap...",
                drug_count,
            )
            try:
                from app.services.drug_ingestion_service import discover_and_ingest
                stats = discover_and_ingest(batch_size=20, max_batches=3)
                logger.info(
                    "Initial ingestion complete: discovered=%d, ingested=%d",
                    stats["discovered"], stats["ingested"],
                )
            except Exception as exc:
                logger.error("Initial ingestion failed: %s", exc, exc_info=True)
        else:
            logger.info("Database has %d drugs. Skipping initial bootstrap.", drug_count)
