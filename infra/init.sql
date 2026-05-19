-- Postgres extensions required by Suture
-- This file is mounted into /docker-entrypoint-initdb.d/ and runs once on first cluster init.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;
