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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "authority": self.authority,
            "document_title": self.document_title,
            "publication_year": self.publication_year,
            "url": self.url,
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
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "adult_dosage": self.adult_dosage,
            "pediatric_dosage": self.pediatric_dosage,
            "renal_adjustment": self.renal_adjustment,
            "hepatic_adjustment": self.hepatic_adjustment,
            "source": self.source.to_dict() if self.source else None,
        }


class SafetyWarning(db.Model):
    __tablename__ = "safety_warnings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    contraindications = db.Column(db.Text)
    black_box_warnings = db.Column(db.Text)
    pregnancy_risk = db.Column(db.String(50))
    lactation_risk = db.Column(db.String(50))
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "contraindications": self.contraindications,
            "black_box_warnings": self.black_box_warnings,
            "pregnancy_risk": self.pregnancy_risk,
            "lactation_risk": self.lactation_risk,
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
    approximate_cost = db.Column(db.String(100))
    generic_available = db.Column(db.Boolean, default=False)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "approximate_cost": self.approximate_cost,
            "generic_available": self.generic_available,
            "source": self.source.to_dict() if self.source else None,
        }


class Reimbursement(db.Model):
    __tablename__ = "reimbursement"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False)
    scheme_name = db.Column(db.String(255), nullable=False)
    coverage_notes = db.Column(db.Text)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.source_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.relationship("Source", lazy="joined")

    def to_dict(self):
        return {
            "scheme_name": self.scheme_name,
            "coverage_notes": self.coverage_notes,
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
