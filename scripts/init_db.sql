-- Inicialización mínima para que SQLAlchemy pueda crear tablas.
-- Requiere PostgreSQL.

CREATE SCHEMA IF NOT EXISTS printing;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'printing' AND t.typname = 'print_job_type'
  ) THEN
    CREATE TYPE printing.print_job_type AS ENUM ('shipping_docs', 'upload');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'printing' AND t.typname = 'print_job_status'
  ) THEN
    CREATE TYPE printing.print_job_status AS ENUM ('pending', 'generating', 'ready', 'printing', 'done', 'error');
  END IF;
END $$;

