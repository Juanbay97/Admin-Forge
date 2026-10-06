-- One-shot additive destination. No legacy import, consumer or public writer.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
CREATE ROLE forge_outbox_writer NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_outbox_writer',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
CREATE TABLE forge.outbox_events (
    event_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES forge.organizations(id),
    actor_id uuid NOT NULL,
    request_id uuid NOT NULL,
    resource_id uuid NOT NULL,
    event_type text NOT NULL CHECK (event_type IN ('membership.updated','department.created')),
    previous_revision bigint NOT NULL CHECK (previous_revision>=0 AND previous_revision<9223372036854775807),
    revision bigint NOT NULL CONSTRAINT outbox_events_revision_check CHECK (revision=previous_revision+1),
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version=1),
    outcome text NOT NULL DEFAULT 'succeeded' CHECK (outcome='succeeded'),
    recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    UNIQUE (organization_id,resource_id,revision)
);
ALTER TABLE forge.outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.outbox_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.outbox_events FROM PUBLIC,forge_runtime,forge_identity_binder,forge_designator;
GRANT USAGE ON SCHEMA forge TO forge_outbox_writer;
GRANT INSERT ON forge.outbox_events TO forge_outbox_writer;
GRANT EXECUTE ON FUNCTION forge.context_organization() TO forge_outbox_writer;
CREATE POLICY outbox_record ON forge.outbox_events FOR INSERT TO forge_outbox_writer
    WITH CHECK (organization_id=forge.context_organization());
COMMIT;
