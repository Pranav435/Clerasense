#!/bin/bash
# Database initialization script for Docker entrypoint
set -e

echo "Initializing Clerasense database..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    \i /docker-entrypoint-initdb.d/01_schema.sql
    \i /docker-entrypoint-initdb.d/02_seed.sql
EOSQL
echo "Database initialization complete."
