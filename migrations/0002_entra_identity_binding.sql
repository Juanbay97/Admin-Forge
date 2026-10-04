-- Additive binding migration. Trusted administrator, dedicated Forge database.
-- LOGIN provisioning and deployment migration orchestration remain external.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
CREATE ROLE forge_identity_binder NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_identity_binder',
                   current_database());
END $$;
SET LOCAL ROLE forge_migrator;
ALTER TABLE forge.identities
    ADD COLUMN entra_tenant_id uuid,
    ADD COLUMN entra_object_id uuid,
    ADD CONSTRAINT entra_binding_consistent CHECK (
        (entra_tenant_id IS NULL AND entra_object_id IS NULL)
        OR (entra_tenant_id IS NOT NULL AND entra_object_id IS NOT NULL
            AND provider = 'entra'
            AND issuer = 'https://login.microsoftonline.com/' || entra_tenant_id::text || '/v2.0'
            AND subject = entra_object_id::text)),
    ADD CONSTRAINT entra_binding_unique UNIQUE (entra_tenant_id, entra_object_id);

CREATE FUNCTION forge.guard_entra_binding() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF OLD.entra_tenant_id IS NOT NULL AND (
        NEW.entra_tenant_id IS DISTINCT FROM OLD.entra_tenant_id
        OR NEW.entra_object_id IS DISTINCT FROM OLD.entra_object_id
        OR NEW.id IS DISTINCT FROM OLD.id
        OR NEW.provider IS DISTINCT FROM OLD.provider
        OR NEW.issuer IS DISTINCT FROM OLD.issuer
        OR NEW.subject IS DISTINCT FROM OLD.subject) THEN
        RAISE EXCEPTION 'Bound identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER entra_binding_write_once BEFORE UPDATE ON forge.identities
    FOR EACH ROW EXECUTE FUNCTION forge.guard_entra_binding();

CREATE FUNCTION forge.binding_identity() RETURNS uuid
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog AS $$
    SELECT CASE WHEN current_setting('forge.binding_identity', true) ~
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('forge.binding_identity', true)::uuid ELSE NULL END
$$;
-- The original organization context must never broaden the binder's self scope.
-- Other policies and their organization/membership semantics are unchanged.
ALTER POLICY identity_scope ON forge.identities TO forge_runtime, forge_migrator;
CREATE POLICY identity_binding_scope ON forge.identities
    FOR ALL TO forge_identity_binder
    USING (
        id = forge.binding_identity()
        AND provider = 'entra'
        AND issuer = current_setting('forge.binding_issuer', true)
        AND subject = current_setting('forge.binding_object', true)
        AND issuer = 'https://login.microsoftonline.com/'
            || current_setting('forge.binding_tenant', true) || '/v2.0'
    )
    WITH CHECK (
        id = forge.binding_identity()
        AND provider = 'entra'
        AND issuer = current_setting('forge.binding_issuer', true)
        AND subject = current_setting('forge.binding_object', true)
        AND issuer = 'https://login.microsoftonline.com/'
            || current_setting('forge.binding_tenant', true) || '/v2.0'
        AND entra_tenant_id::text = current_setting('forge.binding_tenant', true)
        AND entra_object_id::text = current_setting('forge.binding_object', true)
    );
GRANT USAGE ON SCHEMA forge TO forge_identity_binder;
GRANT SELECT ON forge.identities TO forge_identity_binder;
GRANT UPDATE (entra_tenant_id, entra_object_id) ON forge.identities TO forge_identity_binder;
REVOKE ALL ON FUNCTION forge.guard_entra_binding(), forge.binding_identity() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.binding_identity() TO forge_identity_binder;
COMMIT;
