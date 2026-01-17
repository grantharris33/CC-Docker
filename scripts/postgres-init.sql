-- PostgreSQL initialization script for CC-Docker
-- This script runs automatically when the database is first created

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search performance

-- Set default permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ccadmin;

-- Create optimized indexes will be created by SQLAlchemy models
-- This file is primarily for extensions and initial setup

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'CC-Docker database initialized successfully';
END $$;
