-- ================================================================
-- Clerasense – PostgreSQL Schema
-- Normalized relational schema with mandatory source references.
-- ================================================================

-- Sources of medical authority (must be populated before claims)
CREATE TABLE IF NOT EXISTS sources (
    source_id   SERIAL PRIMARY KEY,
    authority   VARCHAR(255) NOT NULL,
    document_title VARCHAR(512) NOT NULL,
    publication_year INT,
    url         TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_sources_authority ON sources(authority);

-- Core drug catalog
CREATE TABLE IF NOT EXISTS drugs (
    id              SERIAL PRIMARY KEY,
    generic_name    VARCHAR(255) NOT NULL UNIQUE,
    brand_names     TEXT[] DEFAULT '{}',
    drug_class      VARCHAR(255),
    mechanism_of_action TEXT,
    source_id       INT NOT NULL REFERENCES sources(source_id),
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_drugs_generic ON drugs(generic_name);
CREATE INDEX idx_drugs_class ON drugs(drug_class);

-- Approved indications
CREATE TABLE IF NOT EXISTS indications (
    id          SERIAL PRIMARY KEY,
    drug_id     INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    approved_use TEXT NOT NULL,
    source_id   INT NOT NULL REFERENCES sources(source_id),
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_indications_drug ON indications(drug_id);

-- Dosage guidelines
CREATE TABLE IF NOT EXISTS dosage_guidelines (
    id                  SERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    adult_dosage        TEXT,
    pediatric_dosage    TEXT,
    renal_adjustment    TEXT,
    hepatic_adjustment  TEXT,
    overdose_info       TEXT,
    underdose_info      TEXT,
    source_id           INT NOT NULL REFERENCES sources(source_id),
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_dosage_drug ON dosage_guidelines(drug_id);

-- Safety warnings
CREATE TABLE IF NOT EXISTS safety_warnings (
    id                  SERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    contraindications   TEXT,
    black_box_warnings  TEXT,
    pregnancy_risk      TEXT,
    lactation_risk      TEXT,
    source_id           INT NOT NULL REFERENCES sources(source_id),
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_safety_drug ON safety_warnings(drug_id);

-- Drug-drug interactions
CREATE TABLE IF NOT EXISTS drug_interactions (
    id                  SERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    interacting_drug    VARCHAR(255) NOT NULL,
    severity            VARCHAR(50) NOT NULL CHECK (severity IN ('minor','moderate','major','contraindicated')),
    description         TEXT NOT NULL,
    source_id           INT NOT NULL REFERENCES sources(source_id),
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_interactions_drug ON drug_interactions(drug_id);
CREATE INDEX idx_interactions_pair ON drug_interactions(drug_id, interacting_drug);

-- Pricing
CREATE TABLE IF NOT EXISTS pricing (
    id                  SERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    approximate_cost    VARCHAR(100),
    generic_available   BOOLEAN DEFAULT FALSE,
    source_id           INT NOT NULL REFERENCES sources(source_id),
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_pricing_drug ON pricing(drug_id);

-- Government reimbursement (country-specific)
CREATE TABLE IF NOT EXISTS reimbursement (
    id              SERIAL PRIMARY KEY,
    drug_id         INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    scheme_name     VARCHAR(255) NOT NULL,
    coverage_notes  TEXT,
    country         VARCHAR(5) NOT NULL DEFAULT 'US',
    source_id       INT NOT NULL REFERENCES sources(source_id),
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_reimbursement_drug ON reimbursement(drug_id);
CREATE INDEX idx_reimbursement_country ON reimbursement(drug_id, country);

-- Doctor accounts
CREATE TABLE IF NOT EXISTS doctors (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    license_number  VARCHAR(100) NOT NULL UNIQUE,
    specialization  VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_doctors_email ON doctors(email);

-- Audit log for every API interaction
CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    doctor_id   INT REFERENCES doctors(id),
    endpoint    VARCHAR(255),
    method      VARCHAR(10),
    request_body TEXT,
    response_summary TEXT,
    was_refused BOOLEAN DEFAULT FALSE,
    refusal_reason TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_audit_doctor ON audit_log(doctor_id);
CREATE INDEX idx_audit_refused ON audit_log(was_refused);

-- Embedding cache for RAG
CREATE TABLE IF NOT EXISTS embeddings (
    id          SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   INT NOT NULL,
    field_name  VARCHAR(100),
    embedding   FLOAT8[] NOT NULL,
    model_name  VARCHAR(100),
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_embeddings_entity ON embeddings(entity_type, entity_id);

-- Ingestion log – tracks background data ingestion from public APIs
CREATE TABLE IF NOT EXISTS ingestion_log (
    id              SERIAL PRIMARY KEY,
    drug_name       VARCHAR(255) NOT NULL,
    source_api      VARCHAR(100) NOT NULL,
    status          VARCHAR(50) NOT NULL CHECK (status IN ('fetched','verified','ingested','failed','skipped','unverified')),
    confidence      FLOAT DEFAULT 0,
    sources_used    TEXT[] DEFAULT '{}',
    conflicts       TEXT,
    details         TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_ingestion_drug ON ingestion_log(drug_name);
CREATE INDEX idx_ingestion_status ON ingestion_log(status);
CREATE INDEX idx_ingestion_created ON ingestion_log(created_at);

-- Brand-level product data (one row per branded / manufactured formulation)
CREATE TABLE IF NOT EXISTS brand_products (
    id                  SERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    brand_name          VARCHAR(300) NOT NULL,
    medicine_name       VARCHAR(500),
    manufacturer        VARCHAR(400),
    ndc                 VARCHAR(50),
    dosage_form         VARCHAR(200),
    strength            VARCHAR(200),
    route               VARCHAR(100),
    is_combination      BOOLEAN DEFAULT FALSE,
    active_ingredients  TEXT,
    inactive_ingredients_summary TEXT,
    product_type        VARCHAR(100),
    nadac_per_unit      FLOAT,
    nadac_unit          VARCHAR(20),
    nadac_effective_date VARCHAR(20),
    approximate_cost    TEXT,
    source_url          TEXT,
    source_authority    VARCHAR(100),
    market_country      VARCHAR(5) DEFAULT 'US' NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_brand_products_drug ON brand_products(drug_id);
CREATE INDEX idx_brand_products_name ON brand_products(brand_name);
CREATE INDEX idx_brand_products_country ON brand_products(market_country);
