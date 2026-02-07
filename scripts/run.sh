#!/usr/bin/env bash
# ==============================================================
# Clerasense – Local Development Server
# ==============================================================
# Starts the Flask backend which also serves the frontend.
# Prerequisites:
#   1. Python venv created:  python3 -m venv venv
#   2. Packages installed:   pip install -r backend/requirements.txt
#   3. .env file configured: cp .env.example .env  (set DATABASE_URL, OPENAI_API_KEY, etc.)
#   4. Database initialized: bash scripts/setup_db.sh
#
# Usage: bash scripts/run.sh
# ==============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Activate venv if it exists
if [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
elif [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
fi

echo "==> Starting Clerasense backend (Flask dev server)..."
echo "    API:      http://127.0.0.1:5000/api/health"
echo "    Frontend: http://127.0.0.1:5000/"
echo ""

cd backend
python wsgi.py
