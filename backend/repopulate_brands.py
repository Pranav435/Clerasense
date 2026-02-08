"""Add medicine_name column and repopulate all brands."""
import sys, os, time
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from app.main import create_app
from app.database import db
from sqlalchemy import text, inspect
from app.models.models import Drug, BrandProduct
from app.services.brand_service import fetch_and_store_brands

app = create_app()

with app.app_context():
    # 1. Column already exists via db.create_all() in create_app
    inspector = inspect(db.engine)
    cols = [c["name"] for c in inspector.get_columns("brand_products")]
    print(f"brand_products columns: {cols}")
    assert "medicine_name" in cols, "medicine_name column missing!"

    # 2. Get drug list first
    drugs = db.session.execute(text("SELECT id, generic_name FROM drugs ORDER BY id")).fetchall()
    total = len(drugs)
    print(f"Found {total} drugs.\n")

    # 3. For each drug, delete its brands and re-fetch
    success = 0
    failed = 0
    for i, (drug_id, gname) in enumerate(drugs, 1):
        try:
            db.session.execute(text("DELETE FROM brand_products WHERE drug_id = :did"), {"did": drug_id})
            db.session.commit()

            drug = db.session.get(Drug, drug_id)
            brands = fetch_and_store_brands(drug)
            print(f"[{i}/{total}] {gname} — {len(brands)} brands.")
            success += 1
        except Exception as e:
            db.session.rollback()
            print(f"[{i}/{total}] {gname} — ERROR: {e}")
            failed += 1
        time.sleep(0.3)

    total_brands = db.session.execute(text("SELECT count(*) FROM brand_products")).scalar()
    print(f"\nDone! Success: {success}, Failed: {failed}")
    print(f"Total brand_products rows: {total_brands}")

    # Verify medicine_name is populated
    rows = db.session.execute(text(
        "SELECT brand_name, medicine_name FROM brand_products LIMIT 5"
    )).fetchall()
    for bn, mn in rows:
        print(f"  [{bn}] medicine_name = {mn}")
