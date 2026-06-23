-- DIGITRANS-CM – Initialisation base de données (environnement dev)
-- Ce script crée les extensions nécessaires et les schémas par module

-- Extensions PostgreSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- chiffrement côté base si nécessaire
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";  -- monitoring requêtes

-- Schémas par module fonctionnel
CREATE SCHEMA IF NOT EXISTS crm;
CREATE SCHEMA IF NOT EXISTS erp;
CREATE SCHEMA IF NOT EXISTS supply_chain;
CREATE SCHEMA IF NOT EXISTS audit;

-- Table d'audit centralisée (conformité loi 2010/012)
CREATE TABLE IF NOT EXISTS audit.access_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id     TEXT,
    action      TEXT NOT NULL,
    resource    TEXT NOT NULL,
    ip_address  INET,
    user_agent  TEXT,
    request_id  TEXT,
    status_code INTEGER,
    duration_ms NUMERIC(10,2)
);

-- Index pour les requêtes d'audit fréquentes
CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON audit.access_log (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_access_log_user_id   ON audit.access_log (user_id);

-- Rôles base de données (moindre privilège)
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_app') THEN
        CREATE ROLE crm_app LOGIN PASSWORD 'devpassword123';
    END IF;
END $$;

GRANT USAGE ON SCHEMA crm, audit TO crm_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA crm TO crm_app;
GRANT INSERT ON audit.access_log TO crm_app;
-- Pas de DELETE ni DROP accordé à l'application
