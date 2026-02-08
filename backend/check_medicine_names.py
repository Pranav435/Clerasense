"""Quick check of medicine_name values for a few drugs."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.main import create_app
from app.database import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    for drug_name in ["Metformin", "Lisinopril", "Atorvastatin"]:
        print(f"\n=== {drug_name} ===")
        rows = db.session.execute(text(
            "SELECT brand_name, medicine_name, strength, dosage_form "
            "FROM brand_products bp JOIN drugs d ON bp.drug_id=d.id "
            "WHERE d.generic_name = :name LIMIT 5"
        ), {"name": drug_name}).fetchall()
        for r in rows:
            print(f"  brand={r[0]:25} medicine={r[1]:45} str={r[2]:15} form={r[3]}")
