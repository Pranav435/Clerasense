#!/usr/bin/env bash
# ==============================================================
# Clerasense – Database Schema & Seed Setup
# ==============================================================
# Runs schema migration and seed data against the DATABASE_URL
# defined in your .env file. Works with any PostgreSQL instance
# (remote hosted, local, etc.).
#
# Prerequisites:
#   - psql CLI installed (brew install libpq / apt install postgresql-client)
#   - DATABASE_URL set in .env
#
# Usage: bash scripts/setup_db.sh
# ==============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env"

# Load DATABASE_URL from .env
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at ${ENV_FILE}"
    echo "       Run: cp .env.example .env  and fill in your DATABASE_URL"
    exit 1
fi

DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d '=' -f2-)

if [[ -z "$DATABASE_URL" ]]; then
    echo "ERROR: DATABASE_URL is not set in .env"
    exit 1
fi

echo "==> Running schema migration..."
psql "${DATABASE_URL}" -f "${PROJECT_ROOT}/database/schema.sql"

echo "==> Seeding reference data..."
psql "${DATABASE_URL}" -f "${PROJECT_ROOT}/database/seed.sql"

echo ""
echo "✅  Database is ready."
