-- Coordinated schema/runtime rollout: legacy readiness intentionally rejects0011.
-- Storage privileges are not human publication authorization.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
CREATE ROLE forge_config_publisher NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_config_publisher', current_database());
END $$;
SET LOCAL ROLE forge_migrator;

ALTER TABLE forge.outbox_events DROP CONSTRAINT outbox_events_event_type_check;
ALTER TABLE forge.outbox_events ADD CONSTRAINT outbox_events_event_type_check
    CHECK (event_type IN ('membership.updated','department.created','model_catalog.published'));
ALTER TABLE forge.outbox_events ADD CONSTRAINT catalog_publication_event_identity
    UNIQUE (event_id,organization_id,resource_id,revision,event_type);
-- The preexisting writer must never acquire publisher authority from the enum.
ALTER POLICY outbox_record ON forge.outbox_events
    WITH CHECK (organization_id=forge.context_organization()
        AND event_type IN ('membership.updated','department.created'));
GRANT INSERT ON forge.outbox_events TO forge_config_publisher;
CREATE POLICY catalog_event ON forge.outbox_events FOR INSERT TO forge_config_publisher
    WITH CHECK (organization_id=forge.context_organization()
        AND event_type='model_catalog.published');

CREATE TABLE forge.active_model_catalogs (
    organization_id uuid PRIMARY KEY,
    router_binding_id uuid NOT NULL,
    catalog_revision bigint NOT NULL,
    event_id uuid NOT NULL,
    event_type text NOT NULL DEFAULT 'model_catalog.published'
        CHECK (event_type='model_catalog.published'),
    FOREIGN KEY (organization_id,router_binding_id,catalog_revision)
        REFERENCES forge.model_catalog_snapshots(organization_id,router_binding_id,revision),
    FOREIGN KEY (event_id,organization_id,router_binding_id,catalog_revision,event_type)
        REFERENCES forge.outbox_events(event_id,organization_id,resource_id,revision,event_type)
);
ALTER TABLE forge.active_model_catalogs ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.active_model_catalogs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.active_model_catalogs FROM PUBLIC,forge_runtime,
    forge_identity_binder,forge_designator,forge_outbox_writer,forge_catalog_writer;
GRANT USAGE ON SCHEMA forge TO forge_config_publisher;
GRANT EXECUTE ON FUNCTION forge.context_organization() TO forge_config_publisher;
GRANT SELECT ON forge.model_catalog_snapshots TO forge_config_publisher;
CREATE POLICY catalog_publisher_read ON forge.model_catalog_snapshots
    FOR SELECT TO forge_config_publisher
    USING (organization_id=forge.context_organization());
GRANT SELECT,INSERT,UPDATE ON forge.active_model_catalogs TO forge_config_publisher;
CREATE POLICY catalog_pointer_read ON forge.active_model_catalogs
    FOR SELECT TO forge_config_publisher
    USING (organization_id=forge.context_organization());
CREATE POLICY catalog_pointer_insert ON forge.active_model_catalogs
    FOR INSERT TO forge_config_publisher
    WITH CHECK (organization_id=forge.context_organization());
CREATE POLICY catalog_pointer_update ON forge.active_model_catalogs
    FOR UPDATE TO forge_config_publisher
    USING (organization_id=forge.context_organization())
    WITH CHECK (organization_id=forge.context_organization());
COMMIT;
