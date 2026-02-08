"""
SQLAlchemy ORM models – mirrors the PostgreSQL schema exactly.
Every medical fact references a source via source_id.
"""

from datetime import datetime
from app.database import db


class Source(db.Model):
    __tablename__ = "sources"

    source_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    authority = db.Column(db.String(255), nullable=False)
    document_title = db.Column(db.String(512), nullable=False)
    publication_year = db.Column(db.Integer)
    url = db.Column(db.Text)
    effective_date = db.Column(db.String(20))     # Label effective date
    data_retrieved_at = db.Column(db.DateTime)     # When data was fetched
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "authority": self.authority,
            "document_title": self.document_title,
            "publication_year": self.publication_year,
            "url": self.url,
            "effective_date": self.effective_date,
            "data_retrieved_at": self.data_retrieved_at.isoformat() if self.data_retrieved_at else None,
        }


class Drug(db.Model):
    __tablename__ = "drugs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    generic_name = db.Column(db.String(255), nullable=False, unique=True)
    brand_names = db.Column(db.ARRAY(db.Text), default=[])
    drug_class = db.Column(db.String(255))
    mechanism_of_action = db.Column(db.Text)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    source = db.relationship("Source", backref="drugs", lazy="joined")
    indications = db.relationship("Indication", backref="drug", lazy="joined", cascade="all, delete-orphan")
    dosage_guidelines = db.relationship("DosageGuideline", backref="drug", lazy="joined", cascade="all, delete-orphan")
    safety_warnings = db.relationship("SafetyWarning", backref="drug", lazy="joined", cascade="all, delete-orphan")
    interactions = db.relationship("DrugInteraction", backref="drug", lazy="joined", cascade="all, delete-orphan")
    pricing = db.relationship("Pricing", backref="drug", lazy="joined", cascade="all, delete-orphan")
    reimbursements = db.relationship("Reimbursement", backref="drug", lazy="joined", cascade="all, delete-orphan")
    brand_products = db.relationship("BrandProduct", backref="drug", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self, include_details=False):
        data = {
            "id": self.id,
            "generic_name": self.generic_name,
            "brand_names": self.brand_names or [],
            "drug_class": self.drug_class,
            "mechanism_of_action": self.mechanism_of_action,
            "source": self.source.to_dict() if self.source else None,
        }
        if include_details:
            data["indications"] = [i.to_dict() for i in self.indications]
            data["dosage_guidelines"] = [d.to_dict() for d in self.dosage_guidelines]
            data["safety_warnings"] = [s.to_dict() for s in self.safety_warnings]
            data["interactions"] = [x.to_dict() for x in self.interactions]
            data["pricing"] = [p.to_dict() for p in self.pricing]
            data["reimbursements"] = [r.to_dict() for r in self.reimbursements]
        return data


class Indication(db.Model):
    __tablename__ = "indications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    approved_use = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "approved_use": self.approved_use,
            "source": self.source.to_dict() if self.source else None,
        }


class DosageGuideline(db.Model):
    __tablename__ = "dosage_guidelines"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    adult_dosage = db.Column(db.Text)
    pediatric_dosage = db.Column(db.Text)
    renal_adjustment = db.Column(db.Text)
    hepatic_adjustment = db.Column(db.Text)
    overdose_info = db.Column(db.Text)
    underdose_info = db.Column(db.Text)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "adult_dosage": self.adult_dosage,
            "pediatric_dosage": self.pediatric_dosage,
            "renal_adjustment": self.renal_adjustment,
            "hepatic_adjustment": self.hepatic_adjustment,
            "overdose_info": self.overdose_info,
            "underdose_info": self.underdose_info,
            "source": self.source.to_dict() if self.source else None,
        }


class SafetyWarning(db.Model):
    __tablename__ = "safety_warnings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    contraindications = db.Column(db.Text)
    black_box_warnings = db.Column(db.Text)
    pregnancy_risk = db.Column(db.Text)
    lactation_risk = db.Column(db.Text)
    adverse_event_count = db.Column(db.Integer)         # FAERS total reports
    adverse_event_serious_count = db.Column(db.Integer) # FAERS serious reports
    top_adverse_reactions = db.Column(db.Text)           # JSON string of top reactions
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        import json
        top_reactions = []
        if self.top_adverse_reactions:
            try:
                top_reactions = json.loads(self.top_adverse_reactions)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "contraindications": self.contraindications,
            "black_box_warnings": self.black_box_warnings,
            "pregnancy_risk": self.pregnancy_risk,
            "lactation_risk": self.lactation_risk,
            "adverse_event_count": self.adverse_event_count,
            "adverse_event_serious_count": self.adverse_event_serious_count,
            "top_adverse_reactions": top_reactions,
            "source": self.source.to_dict() if self.source else None,
        }


class DrugInteraction(db.Model):
    __tablename__ = "drug_interactions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    interacting_drug = db.Column(db.String(255), nullable=False)
    severity = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "interacting_drug": self.interacting_drug,
            "severity": self.severity,
            "description": self.description,
            "source": self.source.to_dict() if self.source else None,
        }


class Pricing(db.Model):
    __tablename__ = "pricing"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    approximate_cost = db.Column(db.Text)          # Human-readable cost description
    generic_available = db.Column(db.Boolean, default=False)
    nadac_per_unit = db.Column(db.Float)           # NADAC price per unit in USD
    nadac_ndc = db.Column(db.String(20))           # National Drug Code
    nadac_effective_date = db.Column(db.String(20))  # NADAC pricing date
    nadac_package_description = db.Column(db.Text) # NDC package description
    pricing_source = db.Column(db.String(50))      # 'NADAC', 'estimate', etc.
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "approximate_cost": self.approximate_cost,
            "generic_available": self.generic_available,
            "nadac_per_unit": self.nadac_per_unit,
            "nadac_ndc": self.nadac_ndc,
            "nadac_effective_date": self.nadac_effective_date,
            "nadac_package_description": self.nadac_package_description,
            "pricing_source": self.pricing_source,
            "source": self.source.to_dict() if self.source else None,
        }


class Reimbursement(db.Model):
    __tablename__ = "reimbursement"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    scheme_name = db.Column(db.String(255), nullable=False)
    coverage_notes = db.Column(db.Text)
    country = db.Column(db.String(5), nullable=False, default="US")
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "scheme_name": self.scheme_name,
            "coverage_notes": self.coverage_notes,
            "country": self.country,
            "source": self.source.to_dict() if self.source else None,
        }


class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    license_number = db.Column(db.String(100), nullable=False, unique=True)
    specialization = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "license_number": self.license_number,
            "specialization": self.specialization,
            "is_active": self.is_active,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"))
    endpoint = db.Column(db.String(255))
    method = db.Column(db.String(10))
    request_body = db.Column(db.Text)
    response_summary = db.Column(db.Text)
    was_refused = db.Column(db.Boolean, default=False)
    refusal_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Embedding(db.Model):
    __tablename__ = "embeddings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    field_name = db.Column(db.String(100))
    embedding = db.Column(db.ARRAY(db.Float), nullable=False)
    model_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IngestionLog(db.Model):
    __tablename__ = "ingestion_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_name = db.Column(db.String(255), nullable=False)
    source_api = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float, default=0)
    sources_used = db.Column(db.ARRAY(db.Text), default=[])
    conflicts = db.Column(db.Text)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BrandProduct(db.Model):
    """Individual branded/manufactured products for a generic drug."""
    __tablename__ = "brand_products"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    brand_name = db.Column(db.String(300), nullable=False)
    medicine_name = db.Column(db.String(500))               # full prescribable name
    manufacturer = db.Column(db.String(400))
    ndc = db.Column(db.String(50))                         # National Drug Code
    dosage_form = db.Column(db.String(200))                # tablet, capsule, injection …
    strength = db.Column(db.String(200))                   # e.g. "500 mg"
    route = db.Column(db.String(100))                      # oral, intravenous …
    is_combination = db.Column(db.Boolean, default=False)  # pure drug vs combo
    active_ingredients = db.Column(db.Text)                 # JSON list
    inactive_ingredients_summary = db.Column(db.Text)       # key excipients
    product_type = db.Column(db.String(100))                # PRESCRIPTION, OTC
    nadac_per_unit = db.Column(db.Float)                    # NADAC price / unit USD
    nadac_unit = db.Column(db.String(20))                   # EA, ML, GM
    nadac_effective_date = db.Column(db.String(20))
    approximate_cost = db.Column(db.Text)                   # human-readable cost
    source_url = db.Column(db.Text)
    source_authority = db.Column(db.String(100))
    market_country = db.Column(db.String(5), default="US", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        active = []
        if self.active_ingredients:
            try:
                active = json.loads(self.active_ingredients)
            except (json.JSONDecodeError, TypeError):
                active = [self.active_ingredients]
        return {
            "id": self.id,
            "drug_id": self.drug_id,
            "brand_name": self.brand_name,
            "medicine_name": self.medicine_name,
            "manufacturer": self.manufacturer,
            "ndc": self.ndc,
            "dosage_form": self.dosage_form,
            "strength": self.strength,
            "route": self.route,
            "is_combination": self.is_combination,
            "active_ingredients": active,
            "inactive_ingredients_summary": self.inactive_ingredients_summary,
            "product_type": self.product_type,
            "nadac_per_unit": self.nadac_per_unit,
            "nadac_unit": self.nadac_unit,
            "nadac_effective_date": self.nadac_effective_date,
            "approximate_cost": self.approximate_cost,
            "source_url": self.source_url,
            "source_authority": self.source_authority,
            "market_country": self.market_country,
        }
