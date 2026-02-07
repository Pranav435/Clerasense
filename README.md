# Clerasense

**AI-Powered Drug Intelligence Platform for Physicians**

Clerasense is a doctor-only web platform that provides verified, source-backed drug information using Retrieval-Augmented Generation (RAG). It is an **information assistant** — not a diagnostic, prescribing, or treatment recommendation tool.

---

## Table of Contents

- [Purpose](#purpose)
- [Architecture Overview](#architecture-overview)
- [Data Flow](#data-flow)
- [Feature Modules](#feature-modules)
- [Safety & Compliance](#safety--compliance)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [Environment Configuration](#environment-configuration)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Deployment](#deployment)
- [Limitations & Disclaimers](#limitations--disclaimers)
- [Project Structure](#project-structure)

---

## Purpose

Clerasense helps licensed physicians:

- Retrieve regulatory-approved drug information (FDA, WHO, etc.)
- Compare drugs on fixed factual parameters (no ranking)
- View contraindications and safety warnings including black box warnings
- Check drug-drug interactions with severity classifications
- View cost estimates and generic alternatives
- Check government reimbursement coverage (Medicare, Medicaid)
- Validate prescription safety constraints (not generate prescriptions)

**Every response is source-backed.** If data is unavailable in verified sources, the system explicitly states so rather than speculating.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Static)                     │
│  HTML/CSS/Vanilla JS  │  Served by Flask                │
│  ┌────────┬────────┬──────────┬──────────┐              │
│  │  Chat  │Compare │ Safety   │ Pricing  │              │
│  └────────┴────────┴──────────┴──────────┘              │
└──────────────────────┬──────────────────────────────────┘
                       │ /api/*
┌──────────────────────▼──────────────────────────────────┐
│                 Backend (Flask)                           │
│  Port 5000                                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │  JWT Auth Middleware → Rate Limiter → Audit Log   │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Intent Classifier → Guardrails → RAG Pipeline    │   │
│  │  (pattern-based)    (refusal)   (retrieve→LLM)    │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌────────────────────┐
│  PostgreSQL      │    │   OpenAI API       │
│  (remote hosted, │    │  (embeddings +     │
│   normalized     │    │   summarization)   │
│   drug data)     │    │                    │
└──────────────────┘    └────────────────────┘
```

### Technology Stack

| Layer      | Technology                         |
|------------|------------------------------------|
| Frontend   | HTML, CSS, Vanilla JavaScript       |
| Backend    | Python 3.12, Flask                 |
| Database   | PostgreSQL 16                      |
| AI/RAG     | OpenAI API (embeddings + GPT-4o-mini) |
| Auth       | JWT (HS256) + bcrypt               |

---

## Data Flow

### Drug Information Chat (RAG Pipeline)

```
Doctor Query
    │
    ▼
1. Intent Classification (pattern-based)
    │
    ├── UNSAFE intent? ──▶ Return structured refusal + log
    │
    ▼
2. Guardrail Content Checks (jailbreak detection)
    │
    ▼
3. Semantic Retrieval (embedding similarity search)
    │
    ├── No results? ──▶ "Not available in verified sources"
    │                    (NO LLM call made)
    ▼
4. Context Building (structured drug data → text block)
    │
    ▼
5. LLM Summarization (GPT-4o-mini, temp=0.1)
    │  System prompt enforces: cite-only, no recommendations,
    │  neutral tone, refuse out-of-scope
    ▼
6. Response with mandatory source citations
    │
    ▼
7. Audit log entry written
```

### Critical Rules

- **No retrieval → No LLM call → No answer** (hard rule)
- **Every factual claim must cite its source**
- **Missing data returns "Not available in verified sources"**
- **Unsafe queries return structured refusals with redirection**

---

## Feature Modules

### 1. Drug Information Chat
Natural language queries about drugs. Returns structured sections: Approved Uses, Dosage Overview, Safety Warnings, Interactions, Regulatory Notes, Sources.

### 2. Drug Comparison
Compare 2–4 drugs on fixed factual dimensions. No ranking or "better than" language. Parameters: drug class, mechanism, indications, dosage, safety, interactions, pricing.

### 3. Prescription Safety Checker
Input drug names + optional context flags (pregnancy, renal impairment, hepatic impairment). Returns: contraindications, interaction alerts with severity, context-specific warnings. Includes mandatory disclaimer banner.

### 4. Pricing & Reimbursement
Displays approximate cost estimates, generic availability, and government coverage scheme information. All prices include variability disclaimer.

---

## Safety & Compliance

### Hard Non-Goals (System Will NEVER)

| Prohibited Action              | Enforcement Mechanism          |
|-------------------------------|-------------------------------|
| Diagnose diseases              | Intent classifier + refusal    |
| Recommend treatments           | Intent classifier + refusal    |
| Suggest "best drug"            | Intent classifier + refusal    |
| Generate prescriptions         | Intent classifier + refusal    |
| Personalize dosages            | Intent classifier + refusal    |
| Address patients directly      | Intent classifier + refusal    |
| Provide speculative answers    | Intent classifier + refusal    |
| Use promotional language       | LLM system prompt enforcement  |

### Guardrail Implementation

1. **Intent Classification**: Regex-based pattern matching classifies queries into safe/unsafe categories before any data retrieval.
2. **Refusal Templates**: Each unsafe intent has a structured refusal message explaining why the request was declined and suggesting safe alternatives.
3. **Jailbreak Detection**: Content-level checks for prompt injection attempts (e.g., "ignore your instructions").
4. **LLM System Prompt**: Redundant safety instructions in the system prompt prevent the LLM from violating boundaries even if classification misses.
5. **Audit Logging**: Every interaction is logged with refusal status for compliance review.
6. **Retrieval Gate**: LLM is only called with retrieved data — it cannot use internal knowledge.

### Refusal Response Format

When a query is refused, the response includes:
- Clear refusal indicator with reason
- Specific explanation of why it was declined
- List of what the system CAN help with
- Suggestion for rephrasing the query

---

## Database Schema

Normalized PostgreSQL schema. All medical facts reference the `sources` table via `source_id` foreign key.

| Table               | Purpose                                    |
|--------------------|--------------------------------------------|
| `sources`          | Authoritative references (FDA, WHO, etc.)  |
| `drugs`            | Core drug catalog (generic name, class, MoA)|
| `indications`      | Approved uses per drug                     |
| `dosage_guidelines`| Adult, pediatric, renal, hepatic dosing    |
| `safety_warnings`  | Contraindications, black box, pregnancy    |
| `drug_interactions`| Drug-drug interactions with severity       |
| `pricing`          | Approximate cost, generic availability     |
| `reimbursement`    | Government coverage schemes                |
| `doctors`          | Authenticated physician accounts           |
| `audit_log`        | Every API interaction for compliance       |
| `embeddings`       | Cached vector embeddings for RAG           |

---

## API Reference

All endpoints require JWT authentication except `/api/auth/*` and `/api/health`.

| Method | Endpoint                     | Description                          |
|--------|------------------------------|--------------------------------------|
| GET    | `/api/health`                | Health check                         |
| POST   | `/api/auth/register`         | Register a new doctor                |
| POST   | `/api/auth/login`            | Login and receive JWT                |
| GET    | `/api/drugs/`                | List/search drugs                    |
| GET    | `/api/drugs/<id>`            | Get full drug profile with sources   |
| GET    | `/api/drugs/by-name/<name>`  | Lookup drug by generic name          |
| POST   | `/api/chat/`                 | RAG-powered drug info chat           |
| POST   | `/api/comparison/`           | Compare 2–4 drugs                    |
| POST   | `/api/safety/check`          | Safety/interaction check             |
| GET    | `/api/pricing/<drug_name>`   | Pricing and reimbursement info       |

### Rate Limiting

Default: 60 requests/minute per IP address.

---

## Environment Configuration

All secrets are managed via `.env` file. **No secrets are hard-coded anywhere in the codebase.**

```bash
# Copy template and fill in real values
cp .env.example .env
```

### Required Variables

| Variable             | Description                           |
|---------------------|---------------------------------------|
| `OPENAI_API_KEY`    | OpenAI API key for RAG pipeline       |
| `DATABASE_URL`      | PostgreSQL connection string          |
| `FLASK_SECRET_KEY`  | Flask session encryption key          |
| `JWT_SECRET`        | JWT token signing secret              |
| `EMBEDDING_MODEL_NAME` | OpenAI embedding model name        |
| `APP_ENV`           | Environment: development/staging/production |

### Security Rules

- `.env` is gitignored and never committed
- Frontend never accesses secret keys
- Backend validates all required variables at startup

---

## Development Setup

### Prerequisites

- **Python 3.12+**
- **PostgreSQL 16** database (remote hosted or local)
- **psql** CLI — for running schema/seed scripts
  - macOS: `brew install libpq`
  - Ubuntu: `sudo apt install postgresql-client`
- An **OpenAI API key** for the RAG pipeline

### 1. Clone & Configure Environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL to your remote PostgreSQL connection string,
# add your OpenAI key, and generate secret keys.
```

### 2. Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Initialize the Database

```bash
bash scripts/setup_db.sh
```

This connects to the PostgreSQL database specified by `DATABASE_URL` in your `.env` file, runs the schema migration, and seeds the initial drug data. Works with any remote or local PostgreSQL instance.

### 4. Start the Server

```bash
bash scripts/run.sh
```

Or manually:

```bash
source venv/bin/activate
cd backend
python wsgi.py
```

### 5. Access the Application

- **Frontend:** http://127.0.0.1:5000/
- **API Health:** http://127.0.0.1:5000/api/health

Flask serves both the API and the frontend static files on port 5000.

---

## Running Tests

```bash
cd backend
pip install pytest
python -m pytest tests/ -v
```

### Test Coverage

- **API tests**: All REST endpoints, authentication, authorization
- **Guardrail tests**: Intent classification accuracy for safe/unsafe queries
- **Refusal tests**: Structured refusal for all prohibited query types
- **Jailbreak tests**: Prompt injection prevention
- **Template completeness**: All unsafe intents have refusal templates

---

## Deployment

### Production Considerations

- Use a WSGI server like **gunicorn** for production:
  ```bash
  pip install gunicorn
  cd backend
  gunicorn wsgi:app --bind 0.0.0.0:5000 --workers 4
  ```
- Use a reverse proxy (e.g., Nginx, Caddy) for TLS/SSL termination
- Set `APP_ENV=production` in `.env`
- Use strong, unique values for `FLASK_SECRET_KEY` and `JWT_SECRET`
- Configure proper CORS origins instead of wildcard
- Set up log aggregation for audit trail
- Regular database backups
- Monitor rate limiting thresholds

---

## Limitations & Disclaimers

### What Clerasense Is

- A **drug information retrieval tool** for licensed physicians
- A source-backed, citation-enforced reference system
- An AI-assisted summarization layer over verified regulatory data

### What Clerasense Is NOT

- A diagnostic tool
- A treatment recommender
- A prescription generator
- A substitute for clinical judgment
- A patient-facing application
- A real-time adverse event reporting system

### Data Limitations

- Drug data is **limited to the seeded database** — not a complete pharmacopeia
- Prices are **approximate estimates** that vary by region, pharmacy, and time
- Reimbursement information reflects general schemes and may not match specific plan details
- The system does not receive real-time FDA safety updates
- Off-label use information may be incomplete

### AI Limitations

- LLM summarization may occasionally rephrase information in ways that alter nuance
- Semantic search may miss relevant drugs if query phrasing differs significantly from indexed data
- The intent classifier uses pattern matching and may misclassify edge-case queries
- Rate of false refusals (safe queries blocked) is non-zero

### Regulatory

This software is provided for **informational purposes only**. It has not been cleared or approved by the FDA or any regulatory body as a clinical decision support system. All information must be independently verified against current prescribing information and clinical guidelines before any clinical use.

---

## Project Structure

```
clerasense/
├── .env.example              # Environment variable template
├── .gitignore
├── README.md
│
├── scripts/
│   ├── setup_db.sh           # Run schema & seed against remote DB
│   └── run.sh                # Start dev server
│
├── backend/
│   ├── requirements.txt
│   ├── wsgi.py               # Entry point (python wsgi.py)
│   ├── pytest.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # Flask app factory + static serving
│   │   ├── config.py         # Environment variable loader
│   │   ├── database.py       # SQLAlchemy instance
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── models.py     # All ORM models
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py       # Registration & login
│   │   │   ├── drugs.py      # Drug CRUD & search
│   │   │   ├── chat.py       # RAG chat endpoint
│   │   │   ├── comparison.py # Drug comparison
│   │   │   ├── safety.py     # Safety checker
│   │   │   └── pricing.py    # Pricing & reimbursement
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── intent_classifier.py  # Query intent detection
│   │   │   ├── guardrails.py         # Safety refusal layer
│   │   │   ├── rag_service.py        # RAG pipeline orchestrator
│   │   │   ├── retrieval_service.py  # Semantic & keyword search
│   │   │   └── embedding_service.py  # Vector embedding generation
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── auth_middleware.py    # JWT validation
│   │       └── audit_logger.py      # Request/response auditing
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py       # Fixtures & test data
│       ├── test_api.py       # API endpoint tests
│       └── test_guardrails.py # Safety & refusal tests
│
├── frontend/
│   ├── index.html
│   ├── css/
│   │   ├── main.css          # Layout & global styles
│   │   └── components.css    # Module-specific components
│   └── js/
│       ├── api.js            # HTTP client (no secrets)
│       ├── auth.js           # Login/register UI
│       ├── app.js            # Shell controller & routing
│       └── modules/
│           ├── chat.js       # Drug info chat
│           ├── comparison.js # Drug comparison
│           ├── safety.js     # Safety checker
│           └── pricing.js    # Pricing & reimbursement
│
└── database/
    ├── schema.sql            # Full normalized schema
    └── seed.sql              # Verified seed data with sources
```
