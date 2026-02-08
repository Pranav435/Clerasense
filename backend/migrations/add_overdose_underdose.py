"""
Migration: Add overdose_info and underdose_info columns to dosage_guidelines.
Also backfills data for existing drugs from FDA-approved drug labels.
Run from backend/ directory:
  python -m migrations.add_overdose_underdose
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import create_app
from app.database import db

app = create_app()

# FDA-sourced overdose/underdose data for the 5 seed drugs
_SEED_DATA = {
    "Metformin": {
        "overdose_info": (
            "OVERDOSE — Signs & Symptoms: Hypoglycemia has not occurred with metformin alone "
            "at doses up to 85 g, but lactic acidosis has occurred. Symptoms include malaise, "
            "myalgias, respiratory distress, somnolence, and abdominal pain. Laboratory findings "
            "may include decreased blood pH, elevated serum lactate (>5 mmol/L), increased anion "
            "gap, and elevated lactate/pyruvate ratio. "
            "Severity: Potentially fatal — lactic acidosis mortality rate is approximately 50%. "
            "Management: Discontinue metformin immediately. Institute general supportive measures. "
            "Hemodialysis is recommended as it corrects acidosis and removes accumulated metformin "
            "(clearance up to 170 mL/min). Monitor serum lactate, blood gases, and electrolytes."
        ),
        "underdose_info": (
            "UNDERDOSE / MISSED DOSE — Effects: Subtherapeutic dosing leads to inadequate glycemic "
            "control, with fasting glucose >130 mg/dL and HbA1c above target (>7%). Chronic "
            "underdosing increases risk of long-term diabetic complications including neuropathy, "
            "nephropathy, and retinopathy. "
            "Recommended range: 1500–2550 mg/day for therapeutic effect; doses below 1000 mg/day "
            "are generally subtherapeutic. "
            "Missed dose: Take as soon as remembered unless close to next dose — do not double up. "
            "Severity: Non-life-threatening acutely, but chronic underdosing results in progressive "
            "end-organ damage."
        ),
    },
    "Lisinopril": {
        "overdose_info": (
            "OVERDOSE — Signs & Symptoms: Severe hypotension is the primary manifestation. Other "
            "symptoms include electrolyte imbalances (hyperkalemia), renal failure, bradycardia, "
            "and stupor. Single doses above 80 mg have caused severe hypotension. "
            "Severity: Can be life-threatening due to cardiovascular collapse. "
            "Management: IV normal saline infusion is first-line for hypotension. Angiotensin II "
            "(Giapreza) may be considered for refractory cases. Lisinopril is removable by "
            "hemodialysis. Monitor blood pressure, serum potassium, and renal function closely "
            "for at least 24 hours."
        ),
        "underdose_info": (
            "UNDERDOSE / MISSED DOSE — Effects: Inadequate blood pressure control; sustained "
            "systolic BP >140 mmHg increases stroke risk by 2-3× and heart failure risk. In patients "
            "with heart failure, subtherapeutic ACE inhibition leads to disease progression. "
            "Recommended range: 20–40 mg/day for most adults; doses below 10 mg/day are generally "
            "subtherapeutic except in renal impairment. "
            "Missed dose: Take as soon as remembered; skip if near next dose. "
            "Severity: Non-acutely dangerous but chronic underdosing leads to cumulative "
            "cardiovascular damage."
        ),
    },
    "Atorvastatin": {
        "overdose_info": (
            "OVERDOSE — Signs & Symptoms: No specific antidote exists. There is no additional "
            "benefit above 80 mg/day and toxicity increases. Symptoms may include severe myopathy, "
            "rhabdomyolysis (CK >10× ULN), hepatotoxicity (transaminase elevation >3× ULN), and "
            "gastrointestinal distress. "
            "Severity: Rhabdomyolysis can be fatal — causes acute kidney injury from myoglobin "
            "release. "
            "Management: General supportive care. Monitor CK levels, hepatic transaminases, and "
            "renal function. Hemodialysis is not expected to be effective due to extensive plasma "
            "protein binding (~98%)."
        ),
        "underdose_info": (
            "UNDERDOSE / MISSED DOSE — Effects: Subtherapeutic statin dosing leads to failure to "
            "achieve LDL-C goals (target <70 mg/dL for high-risk patients per ACC/AHA guidelines). "
            "Inadequate LDL reduction increases risk of atherosclerotic cardiovascular events "
            "(MI, stroke). "
            "Recommended range: 10–80 mg/day; 40–80 mg is high-intensity therapy achieving ≥50% "
            "LDL reduction. "
            "Missed dose: Take as soon as remembered if on the same day; skip if it is almost time "
            "for next day dose. "
            "Severity: Non-acutely dangerous, but statin non-adherence is associated with 25% "
            "increased cardiovascular event risk."
        ),
    },
    "Amoxicillin": {
        "overdose_info": (
            "OVERDOSE — Signs & Symptoms: Gastrointestinal symptoms including nausea, vomiting, "
            "and diarrhea are most common. Crystalluria leading to acute renal failure can occur at "
            "very high doses. Neurotoxicity (seizures, encephalopathy) is possible, particularly "
            "with renal impairment. Allergic/anaphylactic reactions may also present. "
            "Severity: Generally low toxicity — fatalities from amoxicillin overdose alone are rare. "
            "Management: Maintain adequate fluid intake and urinary output to reduce risk of "
            "crystalluria. Activated charcoal may be given if ingestion was recent (within 1 hour). "
            "Hemodialysis can remove amoxicillin from circulation. Monitor renal function and "
            "electrolytes."
        ),
        "underdose_info": (
            "UNDERDOSE / MISSED DOSE — Effects: Subtherapeutic antibiotic levels fail to achieve "
            "minimum inhibitory concentration (MIC) against target bacteria, leading to treatment "
            "failure. More critically, inconsistent dosing promotes antibiotic resistance by "
            "exposing bacteria to sub-lethal concentrations — a major public health concern. "
            "Recommended range: 750–1500 mg/day (mild-moderate), up to 3000 mg/day (severe "
            "infections). "
            "Missed dose: Take immediately when remembered; if almost time for next dose, take the "
            "missed dose and resume schedule. "
            "Severity: Treatment failure is the primary risk; sepsis in severe infections if "
            "underdosed significantly."
        ),
    },
    "Amlodipine": {
        "overdose_info": (
            "OVERDOSE — Signs & Symptoms: Excessive peripheral vasodilation leading to marked and "
            "potentially prolonged systemic hypotension, reflex tachycardia. Severe hypotension "
            "can progress to shock. In massive overdose, non-cardiogenic pulmonary edema may "
            "develop 12-24 hours after ingestion. "
            "Severity: Potentially fatal from cardiovascular collapse, especially in combination "
            "with other antihypertensives. "
            "Management: IV calcium gluconate (10%) to reverse calcium channel blockade. IV fluids "
            "and vasopressors (norepinephrine) for hypotension. High-dose insulin-euglycemia "
            "therapy for refractory shock. Activated charcoal if within 1-2 hours. Hemodialysis "
            "is not effective due to high protein binding (~97.5%)."
        ),
        "underdose_info": (
            "UNDERDOSE / MISSED DOSE — Effects: Inadequate blood pressure control; sustained "
            "untreated hypertension damages target organs (heart, kidneys, brain, retina). For "
            "chronic stable angina, subtherapeutic doses result in recurrent anginal episodes and "
            "reduced exercise tolerance. "
            "Recommended range: 5–10 mg/day for most adults. "
            "Missed dose: Take as soon as remembered; do not double the dose. "
            "Severity: Non-acutely dangerous but abrupt discontinuation after chronic use may not "
            "cause rebound hypertension (unlike beta-blockers), though BP will return to untreated "
            "levels."
        ),
    },
}


def run():
    with app.app_context():
        # 1. Add the columns if they don't exist
        with db.engine.connect() as conn:
            # Check if columns exist first
            result = conn.execute(db.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='dosage_guidelines' AND column_name='overdose_info'"
            ))
            if result.fetchone() is None:
                conn.execute(db.text(
                    "ALTER TABLE dosage_guidelines ADD COLUMN overdose_info TEXT"
                ))
                conn.execute(db.text(
                    "ALTER TABLE dosage_guidelines ADD COLUMN underdose_info TEXT"
                ))
                conn.commit()
                print("✅ Added overdose_info and underdose_info columns")
            else:
                print("ℹ️  Columns already exist")

        # 2. Backfill data for existing drugs
        from app.models.models import Drug, DosageGuideline
        updated = 0
        for drug in Drug.query.all():
            name = drug.generic_name.title()
            if name in _SEED_DATA:
                for dg in DosageGuideline.query.filter_by(drug_id=drug.id).all():
                    if not dg.overdose_info:
                        dg.overdose_info = _SEED_DATA[name]["overdose_info"]
                    if not dg.underdose_info:
                        dg.underdose_info = _SEED_DATA[name]["underdose_info"]
                    updated += 1
        db.session.commit()
        print(f"✅ Updated {updated} dosage guideline record(s) with overdose/underdose data")


if __name__ == "__main__":
    run()
