"""
Country-specific government reimbursement scheme service.

Provides curated, source-verified information about public drug reimbursement
programmes for each supported country. Every scheme entry carries an explicit
source URL pointing to the official government or intergovernmental portal
so physicians and patients can independently verify coverage.

Supported countries:
  US  – Medicare Part D, Medicaid, 340B, VA, Low Income Subsidy
  IN  – PMBJP Jan Aushadhi, NLEM Price Control, Ayushman Bharat PMJAY, CGHS, ESI
  GB  – NHS Prescriptions, NHS Scotland, NHS Wales
  CA  – Provincial Drug Plans, Non-Insured Health Benefits (NIHB)
  AU  – Pharmaceutical Benefits Scheme (PBS), Repatriation PBS

Additional countries fall back to the WHO Essential Medicines List.
"""

import logging
from datetime import datetime

from app.database import db
from app.models.models import Reimbursement, Drug, Source

logger = logging.getLogger("clerasense.reimbursement")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEME REGISTRY –– every entry must cite a specific, verifiable public source
# ═══════════════════════════════════════════════════════════════════════════════

COUNTRY_SCHEMES = {

    # ── United States ─────────────────────────────────────────────────────────
    "US": [
        {
            "scheme": "Medicare Part D",
            "description": (
                "Federal prescription drug coverage for adults 65+ and certain "
                "younger people with disabilities or End-Stage Renal Disease. "
                "Part D plans maintain formularies; most generic drugs are on the "
                "preferred tier with lowest copays."
            ),
            "eligibility": (
                "Enrolled in Medicare Part A/B. Separate Part D plan or Medicare "
                "Advantage with drug coverage (MA-PD) required."
            ),
            "how_to_access": (
                "Use the Medicare Plan Finder at medicare.gov to search which "
                "plans in your area cover this drug and compare copay tiers."
            ),
            "covers_generics": True,
            "covers_brands": "formulary-dependent",
            "source_authority": "CMS",
            "source_title": "Medicare Plan Finder – Prescription Drug Coverage",
            "source_url": "https://www.medicare.gov/plan-compare/",
            "source_year": 2025,
        },
        {
            "scheme": "Medicaid",
            "description": (
                "Joint federal-state programme covering prescription drugs for "
                "low-income individuals. Medicaid must cover all FDA-approved drugs "
                "from manufacturers participating in the Medicaid Drug Rebate "
                "Program, though states may use preferred drug lists."
            ),
            "eligibility": (
                "Income-based; thresholds vary by state. Generally covers "
                "individuals/families below 138% of the Federal Poverty Level "
                "in expansion states."
            ),
            "how_to_access": (
                "Apply through your state Medicaid agency or HealthCare.gov. "
                "Check your state's preferred drug list for specific copay tiers."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "CMS",
            "source_title": "Medicaid Drug Rebate Program – Covered Outpatient Drugs",
            "source_url": "https://www.medicaid.gov/medicaid/prescription-drugs/index.html",
            "source_year": 2025,
        },
        {
            "scheme": "340B Drug Pricing Program",
            "description": (
                "Federal program requiring drug manufacturers to provide outpatient "
                "drugs at significantly reduced prices to eligible health care "
                "organizations (safety-net providers). Savings average 25–50% "
                "below wholesale cost."
            ),
            "eligibility": (
                "Patients treated at 340B-eligible entities: federally qualified "
                "health centres, Ryan White HIV/AIDS clinics, disproportionate "
                "share hospitals, and other qualifying facilities."
            ),
            "how_to_access": (
                "Receive care at a 340B-covered entity. Search for eligible "
                "facilities on the HRSA 340B OPAIS database."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "HRSA",
            "source_title": "340B Drug Pricing Program – HRSA",
            "source_url": "https://www.hrsa.gov/opa",
            "source_year": 2025,
        },
        {
            "scheme": "Medicare Extra Help (Low Income Subsidy)",
            "description": (
                "Federal programme that helps people with limited income and "
                "resources pay for Medicare Part D premiums, deductibles, and "
                "copays. Full Extra Help limits copays to ~$4.50 (generic) / "
                "$11.20 (brand) per prescription in 2025."
            ),
            "eligibility": (
                "Annual income below $22,590 (individual) / $30,660 (couple) "
                "and resources below $17,220 / $34,360 (2025 thresholds)."
            ),
            "how_to_access": (
                "Apply at ssa.gov/medicare/part-d-extra-help or contact your "
                "local Social Security office. Automatic enrollment for "
                "Medicaid/SSI recipients."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "SSA/CMS",
            "source_title": "Medicare Extra Help with Prescription Drug Costs",
            "source_url": "https://www.ssa.gov/medicare/part-d-extra-help",
            "source_year": 2025,
        },
    ],

    # ── India ─────────────────────────────────────────────────────────────────
    "IN": [
        {
            "scheme": "Pradhan Mantri Bhartiya Janaushadhi Pariyojana (PMBJP)",
            "description": (
                "Government programme providing quality generic medicines at "
                "50–90% lower prices than branded equivalents through Jan Aushadhi "
                "Kendras (dedicated stores). Over 1,900 medicines and 290 "
                "surgical/medical devices available."
            ),
            "eligibility": (
                "Open to all Indian citizens. No income or insurance criterion. "
                "Available at 10,000+ Jan Aushadhi Kendras across India."
            ),
            "how_to_access": (
                "Visit the nearest Jan Aushadhi Kendra. Search for available "
                "medicines and store locations on janaushadhi.gov.in or the "
                "Jan Aushadhi Sugam mobile app."
            ),
            "covers_generics": True,
            "covers_brands": False,
            "source_authority": "BPPI / Ministry of Chemicals & Fertilizers",
            "source_title": "Pradhan Mantri Bhartiya Janaushadhi Pariyojana (PMBJP)",
            "source_url": "https://janaushadhi.gov.in/",
            "source_year": 2025,
        },
        {
            "scheme": "National List of Essential Medicines (NLEM) – Price Control",
            "description": (
                "Drugs on the NLEM are subject to price caps set by the National "
                "Pharmaceutical Pricing Authority (NPPA) under the Drug Price "
                "Control Order (DPCO 2013). Ceiling prices apply to all brands "
                "of scheduled formulations, ensuring affordable access."
            ),
            "eligibility": (
                "Applies to all consumers purchasing NLEM-scheduled drugs. "
                "No individual eligibility required — price caps are enforced "
                "at the point of sale."
            ),
            "how_to_access": (
                "NLEM drugs are available at capped prices at any pharmacy. "
                "Verify ceiling prices on the NPPA portal (nppaindia.nic.in)."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "NPPA / Ministry of Health & Family Welfare",
            "source_title": "National List of Essential Medicines (NLEM 2022) & DPCO 2013",
            "source_url": "https://nppaindia.nic.in/en/drugs/nlem/",
            "source_year": 2022,
        },
        {
            "scheme": "Ayushman Bharat – Pradhan Mantri Jan Arogya Yojana (PMJAY)",
            "description": (
                "India's largest government health insurance scheme providing "
                "₹5 lakh/family/year for secondary and tertiary hospitalisation. "
                "Covers medicines during in-patient treatment. Does NOT directly "
                "cover outpatient prescriptions purchased at pharmacies."
            ),
            "eligibility": (
                "Bottom 40% of deprived households as per SECC 2011 data. "
                "~55 crore beneficiaries. Eligibility can be checked at "
                "mera.pmjay.gov.in."
            ),
            "how_to_access": (
                "Get Ayushman Card (free) at any Common Service Centre (CSC) "
                "or empanelled hospital. Present at any PMJAY-empanelled hospital "
                "for cashless treatment including medicines during admission."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "National Health Authority",
            "source_title": "Ayushman Bharat PMJAY – Official Portal",
            "source_url": "https://pmjay.gov.in/",
            "source_year": 2025,
            "inpatient_only": True,
        },
        {
            "scheme": "Central Government Health Scheme (CGHS)",
            "description": (
                "Healthcare scheme for serving and retired central government "
                "employees and pensioners. Covers approved medicines dispensed "
                "through CGHS wellness centres and empanelled pharmacies."
            ),
            "eligibility": (
                "Serving/retired central government employees, members of "
                "Parliament, ex-governors, freedom fighters, journalists "
                "accredited to PIB, and their dependents."
            ),
            "how_to_access": (
                "Obtain CGHS card → collect medicines from CGHS wellness centre "
                "or empanelled pharmacy with valid prescription. Drug list at "
                "cghs.gov.in."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "Ministry of Health & Family Welfare",
            "source_title": "Central Government Health Scheme (CGHS)",
            "source_url": "https://cghs.gov.in/",
            "source_year": 2025,
        },
        {
            "scheme": "Employees' State Insurance (ESI)",
            "description": (
                "Social security scheme for organised sector workers earning "
                "≤₹21,000/month. Provides full medical care including outpatient "
                "medicines dispensed at ESI dispensaries and hospitals."
            ),
            "eligibility": (
                "Employees in ESI-covered establishments with salary "
                "≤₹21,000/month. Dependents (spouse, children, parents) covered."
            ),
            "how_to_access": (
                "Visit ESI dispensary/hospital with ESI e-Pehchan card. "
                "Medicines dispensed free from ESI pharmacies."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "ESIC / Ministry of Labour & Employment",
            "source_title": "Employees' State Insurance Corporation (ESIC)",
            "source_url": "https://www.esic.gov.in/",
            "source_year": 2025,
        },
    ],

    # ── United Kingdom ────────────────────────────────────────────────────────
    "GB": [
        {
            "scheme": "NHS Prescriptions (England)",
            "description": (
                "Prescription medicines are subsidised by the National Health "
                "Service. A flat charge of £9.90 per item applies in England "
                "(2024/25). Over 89% of prescriptions are dispensed free due "
                "to exemption categories."
            ),
            "eligibility": (
                "All UK residents registered with an NHS GP. Free prescriptions "
                "for: under-16s, 16-18 in education, over-60s, pregnant women, "
                "certain medical conditions (diabetes, epilepsy, etc.), "
                "low income (HC2 certificate), universal credit recipients."
            ),
            "how_to_access": (
                "GP or hospital prescriber issues an NHS prescription; collect "
                "from any pharmacy. Apply for exemption certificates via NHSBSA "
                "or check eligibility at nhsbsa.nhs.uk."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "NHSBSA",
            "source_title": "NHS Prescription Charges – NHS Business Services Authority",
            "source_url": "https://www.nhsbsa.nhs.uk/help-nhs-prescription-costs",
            "source_year": 2025,
        },
        {
            "scheme": "NHS Prescription Prepayment Certificate (PPC)",
            "description": (
                "Flat-rate certificate covering unlimited NHS prescriptions. "
                "3-month PPC costs £32.05; 12-month PPC costs £111.60 (2024/25). "
                "Saves money for patients needing 4+ items in 3 months or "
                "12+ in 12 months."
            ),
            "eligibility": (
                "Any patient paying NHS prescription charges. Can be bought "
                "online, by phone, or at some pharmacies."
            ),
            "how_to_access": (
                "Purchase at nhsbsa.nhs.uk/help-nhs-prescription-costs/"
                "prescription-prepayment-certificates or call 0300 330 1341."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "NHSBSA",
            "source_title": "Prescription Prepayment Certificates",
            "source_url": "https://www.nhsbsa.nhs.uk/help-nhs-prescription-costs/prescription-prepayment-certificates",
            "source_year": 2025,
        },
        {
            "scheme": "NHS Scotland – Free Prescriptions",
            "description": (
                "All NHS prescriptions in Scotland are free at the point of "
                "dispensing for Scottish residents, regardless of income or age."
            ),
            "eligibility": "All residents registered with an NHS Scotland GP.",
            "how_to_access": "Present NHS prescription at any Scottish pharmacy.",
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "NHS Scotland",
            "source_title": "NHS Scotland – Prescriptions",
            "source_url": "https://www.nhsinform.scot/care-support-and-rights/nhs-services/pharmacy/prescriptions/",
            "source_year": 2025,
        },
    ],

    # ── Canada ────────────────────────────────────────────────────────────────
    "CA": [
        {
            "scheme": "Provincial Drug Benefit Programs",
            "description": (
                "Each Canadian province/territory operates its own public drug "
                "plan covering essential prescription medicines. Ontario: ODB / "
                "Trillium; BC: PharmaCare; Quebec: RAMQ; Alberta: non-group "
                "coverage. Plans typically cover drugs on the provincial formulary."
            ),
            "eligibility": (
                "Varies by province. Generally available to seniors (65+), "
                "social assistance recipients, and low-income residents. Some "
                "provinces cover all residents (e.g., BC PharmaCare Fair "
                "PharmaCare is income-based)."
            ),
            "how_to_access": (
                "Contact your provincial ministry of health or check the "
                "formulary search tool on your province's drug plan website."
            ),
            "covers_generics": True,
            "covers_brands": "formulary-dependent",
            "source_authority": "Government of Canada / Provincial Ministries",
            "source_title": "Canada's Public Drug Benefit Programs",
            "source_url": "https://www.canada.ca/en/health-canada/services/health-care-system/pharmaceuticals/access-insurance-coverage-prescription-medicines.html",
            "source_year": 2025,
        },
        {
            "scheme": "Non-Insured Health Benefits (NIHB)",
            "description": (
                "Federal programme providing drug coverage for registered First "
                "Nations and recognized Inuit. Covers a wide formulary of "
                "prescription drugs, OTC medications, and medical supplies."
            ),
            "eligibility": (
                "Registered First Nations (Indian Act status) and recognized Inuit."
            ),
            "how_to_access": (
                "Present NIHB client identification at the pharmacy. Most drugs "
                "on the NIHB formulary are processed automatically (no prior "
                "approval needed)."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "Indigenous Services Canada",
            "source_title": "Non-Insured Health Benefits (NIHB) – Drug Benefits",
            "source_url": "https://www.sac-isc.gc.ca/eng/1572888328565/1572888420703",
            "source_year": 2025,
        },
    ],

    # ── Australia ──────────────────────────────────────────────────────────────
    "AU": [
        {
            "scheme": "Pharmaceutical Benefits Scheme (PBS)",
            "description": (
                "Australian Government programme subsidising prescription medicines. "
                "General patients pay up to $31.60 per script; concessional "
                "patients (pension/healthcare card holders) pay up to $7.70 "
                "(2024 thresholds). Safety net thresholds further reduce costs "
                "for high-use patients."
            ),
            "eligibility": (
                "All Australian residents and eligible visitors with a Medicare "
                "card or reciprocal health care agreement."
            ),
            "how_to_access": (
                "Prescriber writes a PBS prescription; present at any pharmacy. "
                "Search the PBS schedule at pbs.gov.au to check if a specific "
                "drug and indication is listed."
            ),
            "covers_generics": True,
            "covers_brands": "if PBS-listed",
            "source_authority": "Australian Government – Dept of Health",
            "source_title": "Pharmaceutical Benefits Scheme (PBS)",
            "source_url": "https://www.pbs.gov.au/",
            "source_year": 2025,
        },
        {
            "scheme": "Repatriation PBS (RPBS)",
            "description": (
                "Extended pharmaceutical benefits for eligible veterans and "
                "war widows/widowers. Covers a broader range of items than "
                "the standard PBS, including some items not PBS-listed."
            ),
            "eligibility": (
                "Veterans with a DVA Gold or White Repatriation Health Card."
            ),
            "how_to_access": (
                "Present DVA health card and prescription at any pharmacy."
            ),
            "covers_generics": True,
            "covers_brands": True,
            "source_authority": "DVA / Australian Government",
            "source_title": "Repatriation Pharmaceutical Benefits Scheme",
            "source_url": "https://www.dva.gov.au/health-and-treatment/pharmacy-and-medicines",
            "source_year": 2025,
        },
    ],
}

# ── WHO Essential Medicines List (fallback for unsupported countries) ─────
WHO_EML_SCHEME = {
    "scheme": "WHO Model List of Essential Medicines",
    "description": (
        "The World Health Organization's Essential Medicines List (EML) "
        "identifies medicines that satisfy the priority health needs of "
        "the population. Most countries base their national essential medicine "
        "lists on the WHO EML, and listed medicines are typically covered "
        "by government health programmes."
    ),
    "eligibility": (
        "Coverage depends on your country's national essential medicines list "
        "and public health insurance scheme. Check with your national health "
        "authority."
    ),
    "how_to_access": (
        "Consult your national essential medicines list or contact the "
        "relevant ministry of health. The WHO EML is available at "
        "who.int/groups/expert-committee-on-selection-and-use-of-essential-medicines."
    ),
    "covers_generics": True,
    "covers_brands": "varies",
    "source_authority": "WHO",
    "source_title": "WHO Model List of Essential Medicines (24th list, 2025)",
    "source_url": "https://www.who.int/groups/expert-committee-on-selection-and-use-of-essential-medicines/essential-medicines-lists",
    "source_year": 2025,
}

# ── Common drug classes known to be broadly covered ──
BROADLY_COVERED_CLASSES = {
    "antihypertensive", "antidiabetic", "statin", "antibiotic",
    "analgesic", "antipyretic", "antiplatelet", "antiepileptic",
    "bronchodilator", "corticosteroid", "diuretic", "antidepressant",
    "antipsychotic", "anticoagulant", "proton pump inhibitor",
    "angiotensin receptor blocker", "beta blocker", "calcium channel blocker",
    "ace inhibitor", "nsaid", "opioid analgesic",
}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def get_reimbursement_info(drug: Drug, country: str) -> list[dict]:
    """
    Return country-specific government reimbursement scheme information
    for a given drug.

    Each returned dict contains:
      - scheme_name, description, eligibility, how_to_access
      - coverage_status: 'likely_covered' | 'may_be_covered' | 'check_formulary'
      - coverage_note: drug-specific note
      - source: full source dict for the frontend source badge

    Always returns data from the curated scheme registry (fast, in-memory).
    Writes to the reimbursement table for audit/history only.
    """
    country = (country or "US").upper().strip()

    # Always generate from curated schemes (fast, in-memory)
    schemes = COUNTRY_SCHEMES.get(country, [])
    if not schemes:
        # Fallback to WHO EML
        schemes = [WHO_EML_SCHEME]

    results = []
    # Check if we already stored records for this drug+country (avoid duplicates)
    existing_count = Reimbursement.query.filter_by(drug_id=drug.id, country=country).count()

    for scheme_data in schemes:
        coverage = _assess_coverage(drug, scheme_data, country)
        result = {
            "scheme_name": scheme_data["scheme"],
            "description": scheme_data["description"],
            "eligibility": scheme_data.get("eligibility", ""),
            "how_to_access": scheme_data.get("how_to_access", ""),
            "coverage_status": coverage["status"],
            "coverage_note": coverage["note"],
            "inpatient_only": scheme_data.get("inpatient_only", False),
            "source": {
                "authority": scheme_data["source_authority"],
                "document_title": scheme_data["source_title"],
                "url": scheme_data["source_url"],
                "publication_year": scheme_data["source_year"],
                "data_retrieved_at": datetime.utcnow().isoformat(),
            },
        }
        results.append(result)

        # Cache in DB only if not already stored
        if existing_count == 0:
            try:
                src = _get_or_create_source(
                    authority=scheme_data["source_authority"],
                    title=scheme_data["source_title"],
                    url=scheme_data["source_url"],
                    year=scheme_data["source_year"],
                )
                notes = _build_coverage_notes(result)
                reimb = Reimbursement(
                    drug_id=drug.id,
                    scheme_name=scheme_data["scheme"],
                    coverage_notes=notes,
                    country=country,
                    source_id=src.source_id,
                )
                db.session.add(reimb)
            except Exception as exc:
                logger.warning("Failed to cache reimbursement for %s/%s: %s",
                               drug.generic_name, scheme_data["scheme"], exc)

    if existing_count == 0:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return results


def get_supported_countries() -> list[dict]:
    """Return list of countries with curated reimbursement data."""
    country_names = {
        "US": "United States",
        "IN": "India",
        "GB": "United Kingdom",
        "CA": "Canada",
        "AU": "Australia",
    }
    return [
        {"code": code, "name": country_names.get(code, code)}
        for code in COUNTRY_SCHEMES
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _assess_coverage(drug: Drug, scheme: dict, country: str) -> dict:
    """
    Determine likely coverage status of a drug under a given scheme.
    Uses drug class, generic availability, and scheme rules.
    """
    generic_name = (drug.generic_name or "").lower()
    drug_class = (drug.drug_class or "").lower()
    has_generic = bool(drug.pricing and any(p.generic_available for p in drug.pricing))

    # Check if drug class is broadly covered
    class_covered = any(cls in drug_class for cls in BROADLY_COVERED_CLASSES)

    # Scheme-specific logic
    covers_generics = scheme.get("covers_generics", True)
    covers_brands = scheme.get("covers_brands", False)
    inpatient_only = scheme.get("inpatient_only", False)

    if inpatient_only:
        return {
            "status": "inpatient_only",
            "note": (
                f"This scheme covers medicines during in-patient hospitalisation. "
                f"{drug.generic_name} would be covered if part of your hospital "
                f"treatment package. Outpatient pharmacy purchases are not covered."
            ),
        }

    if covers_generics and has_generic and class_covered:
        return {
            "status": "likely_covered",
            "note": (
                f"{drug.generic_name} is a generic {drug_class} medicine. "
                f"Drugs in this class are commonly included on standard formularies. "
                f"Verify specific coverage with the scheme."
            ),
        }

    if covers_generics and has_generic:
        return {
            "status": "likely_covered",
            "note": (
                f"Generic {drug.generic_name} is available. This scheme covers "
                f"generic medicines. Confirm inclusion on the scheme formulary."
            ),
        }

    if covers_brands is True:
        return {
            "status": "may_be_covered",
            "note": (
                f"{drug.generic_name} may be covered. This scheme includes both "
                f"generic and brand-name drugs. Check the specific formulary."
            ),
        }

    if covers_brands == "formulary-dependent":
        return {
            "status": "check_formulary",
            "note": (
                f"Coverage for {drug.generic_name} depends on the specific "
                f"formulary. Check the plan formulary for tier placement and "
                f"any prior authorization requirements."
            ),
        }

    return {
        "status": "check_formulary",
        "note": (
            f"Check whether {drug.generic_name} is listed on the scheme formulary. "
            f"Contact the programme directly for coverage details."
        ),
    }


def _build_coverage_notes(result: dict) -> str:
    """Build a combined coverage notes string for DB storage."""
    parts = []
    if result.get("coverage_status"):
        parts.append(f"Status: {result['coverage_status']}")
    if result.get("coverage_note"):
        parts.append(result["coverage_note"])
    if result.get("eligibility"):
        parts.append(f"Eligibility: {result['eligibility']}")
    if result.get("how_to_access"):
        parts.append(f"Access: {result['how_to_access']}")
    return " | ".join(parts)


def _get_or_create_source(authority: str, title: str, url: str, year: int) -> Source:
    """Find or create a Source record for a reimbursement scheme."""
    existing = Source.query.filter_by(authority=authority, url=url).first()
    if existing:
        return existing

    src = Source(
        authority=authority,
        document_title=title,
        url=url,
        publication_year=year,
        data_retrieved_at=datetime.utcnow(),
    )
    db.session.add(src)
    db.session.flush()
    return src
