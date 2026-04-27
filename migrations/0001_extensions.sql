-- Migration 0001 : Extensions PostgreSQL requises.
-- Référence : docs/specs/01-data-model.md § Extensions PostgreSQL requises.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
