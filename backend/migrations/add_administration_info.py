"""
Migration: Add administration_info column to dosage_guidelines.
Also backfills data for existing drugs with FDA-sourced administration details.
Run from backend/ directory:
  python -m migrations.add_administration_info
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import create_app
from app.database import db

app = create_app()

# FDA-sourced administration data for the 5 seed drugs
_SEED_DATA = {
    "Metformin": (
        "Route: Oral. "
        "Available forms: Immediate-release tablets (500 mg, 850 mg, 1000 mg); "
        "extended-release tablets (500 mg, 750 mg, 1000 mg); oral solution (500 mg/5 mL). "
        "Administration: Take with meals to reduce gastrointestinal side effects. "
        "Swallow extended-release tablets whole — do not crush, cut, or chew. "
        "Oral solution may be used for patients who cannot swallow tablets. "
        "Storage: Store at 20–25°C (68–77°F); excursions permitted to 15–30°C. "
        "Keep container tightly closed. Protect from light and moisture."
    ),
    "Lisinopril": (
        "Route: Oral. "
        "Available forms: Tablets (2.5 mg, 5 mg, 10 mg, 20 mg, 30 mg, 40 mg); "
        "oral solution (1 mg/mL). "
        "Administration: May be taken with or without food. Administer once daily "
        "at approximately the same time each day. Tablets may be crushed if needed. "
        "For oral solution, shake well before each use. "
        "Storage: Store at 20–25°C (68–77°F); excursions permitted to 15–30°C. "
        "Protect from moisture and freezing."
    ),
    "Atorvastatin": (
        "Route: Oral. "
        "Available forms: Tablets (10 mg, 20 mg, 40 mg, 80 mg). "
        "Administration: May be taken with or without food, at any time of day. "
        "Swallow tablets whole with water. Consistent daily dosing is recommended. "
        "Unlike some other statins, atorvastatin does not need to be taken at bedtime "
        "due to its long half-life (14 hours for active metabolites). "
        "Storage: Store at 20–25°C (68–77°F). Keep in original container. "
        "Protect from light and moisture."
    ),
    "Amoxicillin": (
        "Route: Oral. "
        "Available forms: Capsules (250 mg, 500 mg); tablets (500 mg, 875 mg); "
        "chewable tablets (125 mg, 250 mg); oral suspension (125 mg/5 mL, 200 mg/5 mL, "
        "250 mg/5 mL, 400 mg/5 mL). "
        "Administration: May be taken with or without food. Take at evenly spaced intervals "
        "to maintain consistent blood levels. Capsules should be swallowed whole. "
        "Chewable tablets must be chewed or crushed before swallowing. "
        "Oral suspension: Shake well before each use; refrigerate reconstituted suspension; "
        "discard unused portion after 14 days. "
        "Storage: Capsules/tablets at 20–25°C (68–77°F). "
        "Reconstituted suspension: refrigerate at 2–8°C."
    ),
    "Amlodipine": (
        "Route: Oral. "
        "Available forms: Tablets (2.5 mg, 5 mg, 10 mg); oral suspension may be compounded. "
        "Administration: May be taken with or without food. Administer once daily. "
        "Tablets may be crushed and mixed with water or applesauce for patients "
        "with difficulty swallowing. "
        "Storage: Store at 15–30°C (59–86°F). Protect from light and moisture. "
        "Dispense in tight, light-resistant container."
    ),
}


def run():
    with app.app_context():
        # 1. Add column if it doesn't exist
        result = db.session.execute(db.text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'dosage_guidelines'
              AND column_name = 'administration_info'
        """))
        if result.fetchone() is None:
            db.session.execute(db.text(
                "ALTER TABLE dosage_guidelines ADD COLUMN administration_info TEXT"
            ))
            db.session.commit()
            print("[migration] Added administration_info column to dosage_guidelines")
        else:
            print("[migration] Column administration_info already exists — skipping DDL")

        # 2. Backfill data for existing drugs
        for drug_name, admin_text in _SEED_DATA.items():
            res = db.session.execute(db.text("""
                UPDATE dosage_guidelines dg
                SET administration_info = :admin
                FROM drugs d
                WHERE dg.drug_id = d.id
                  AND LOWER(d.generic_name) = LOWER(:name)
                  AND (dg.administration_info IS NULL OR dg.administration_info = '')
            """), {"admin": admin_text, "name": drug_name})
            if res.rowcount:
                print(f"  [seed] {drug_name}: backfilled administration_info ({res.rowcount} row(s))")
            else:
                print(f"  [seed] {drug_name}: already has data or not found — skipped")

        db.session.commit()
        print("[migration] Done.")


if __name__ == "__main__":
    run()
