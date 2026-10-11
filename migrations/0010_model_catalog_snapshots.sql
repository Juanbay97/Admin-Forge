-- Unpublished private snapshots only. No active pointer or employee privilege.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
CREATE ROLE forge_catalog_writer NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_catalog_writer', current_database());
END $$;
SET LOCAL ROLE forge_migrator;
CREATE TABLE forge.model_catalog_snapshots (
    organization_id uuid NOT NULL REFERENCES forge.organizations(id),
    router_binding_id uuid NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    payload text NOT NULL CHECK (octet_length(payload) BETWEEN 1 AND 1048576),
    payload_sha256 text NOT NULL CHECK (
        payload_sha256 = encode(sha256(convert_to(payload, 'UTF8')), 'hex')),
    recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    PRIMARY KEY (organization_id, router_binding_id, revision),
    -- Row correlation is enforced in SQL; full typed/canonical validation is
    -- repeated by the private adapter on every read, including privileged damage.
    CHECK ((jsonb_typeof(payload::jsonb) = 'object'
        AND payload::jsonb -> 'schema_version' = '1'::jsonb
        AND payload::jsonb ->> 'organization_id' = organization_id::text
        AND payload::jsonb ->> 'router_binding_id' = router_binding_id::text
        AND payload::jsonb -> 'revision' = to_jsonb(revision)
        AND jsonb_typeof(payload::jsonb -> 'aliases') = 'array') IS TRUE)
);
ALTER TABLE forge.model_catalog_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.model_catalog_snapshots FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.model_catalog_snapshots FROM PUBLIC, forge_runtime,
    forge_identity_binder, forge_designator, forge_outbox_writer;
GRANT USAGE ON SCHEMA forge TO forge_catalog_writer;
GRANT SELECT, INSERT ON forge.model_catalog_snapshots TO forge_catalog_writer;
GRANT EXECUTE ON FUNCTION forge.context_organization() TO forge_catalog_writer;
CREATE POLICY catalog_read ON forge.model_catalog_snapshots FOR SELECT TO forge_catalog_writer
    USING (organization_id = forge.context_organization());
CREATE POLICY catalog_insert ON forge.model_catalog_snapshots FOR INSERT TO forge_catalog_writer
    WITH CHECK (organization_id = forge.context_organization());
COMMIT;
