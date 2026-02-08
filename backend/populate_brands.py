"""
One-off script to populate brand_products for all drugs currently in the DB.
Run from backend/ directory:
    python populate_brands.py
"""
import sys, os, time

sys.path.insert(0, os.path.dirname(__file__))

from app.main import create_app
from app.database import db
from app.models.models import Drug, BrandProduct
from app.services.brand_service import fetch_and_store_brands

app = create_app()

with app.app_context():
    drugs = Drug.query.order_by(Drug.id).all()
    total = len(drugs)
    print(f"Found {total} drugs in DB. Populating brands...\n")

    success = 0
    skipped = 0
    failed = 0

    for i, drug in enumerate(drugs, 1):
        existing = BrandProduct.query.filter_by(drug_id=drug.id).count()
        if existing > 0:
            print(f"[{i}/{total}] {drug.generic_name} — already has {existing} brands, skipping.")
            skipped += 1
            continue

        try:
            brands = fetch_and_store_brands(drug)
            count = len(brands)
            print(f"[{i}/{total}] {drug.generic_name} — {count} brands stored.")
            success += 1
        except Exception as e:
            print(f"[{i}/{total}] {drug.generic_name} — ERROR: {e}")
            failed += 1

        # Small delay to avoid rate-limiting
        time.sleep(0.5)

    print(f"\nDone! Success: {success}, Skipped: {skipped}, Failed: {failed}")
    total_brands = BrandProduct.query.count()
    print(f"Total brand_products rows in DB: {total_brands}")
