-- Storage prerequisite only; bearer verification/publication service remain absent.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
CREATE ROLE forge_catalog_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_catalog_authority;
GRANT EXECUTE ON FUNCTION forge.context_organization(),forge.context_ready(),
    forge.has_membership(uuid) TO forge_catalog_authority;
GRANT SELECT ON forge.organizations,forge.memberships,forge.identities,
    forge.membership_roles TO forge_catalog_authority;
-- PostgreSQL row locks require UPDATE on a column. Callers receive none.
GRANT UPDATE(id) ON forge.organizations,forge.identities TO forge_catalog_authority;
GRANT UPDATE(organization_id) ON forge.memberships,forge.membership_roles
    TO forge_catalog_authority;
-- Restrictive checks also constrain older PUBLIC policies; actual updates deny.
CREATE POLICY catalog_authority_allow ON forge.organizations TO forge_catalog_authority
    USING (id=forge.context_organization()) WITH CHECK (false);
CREATE POLICY catalog_authority_limit ON forge.organizations AS RESTRICTIVE
    TO forge_catalog_authority USING (id=forge.context_organization()) WITH CHECK (false);
CREATE POLICY catalog_authority_allow ON forge.memberships TO forge_catalog_authority
    USING (organization_id=forge.context_organization()) WITH CHECK (false);
CREATE POLICY catalog_authority_limit ON forge.memberships AS RESTRICTIVE
    TO forge_catalog_authority USING (organization_id=forge.context_organization())
    WITH CHECK (false);
CREATE POLICY catalog_authority_allow ON forge.identities TO forge_catalog_authority
    USING (provider='entra' AND issuer=current_setting('forge.issuer',true)
        AND subject=current_setting('forge.subject',true)) WITH CHECK (false);
CREATE POLICY catalog_authority_limit ON forge.identities AS RESTRICTIVE
    TO forge_catalog_authority
    USING (provider='entra' AND issuer=current_setting('forge.issuer',true)
        AND subject=current_setting('forge.subject',true)) WITH CHECK (false);
CREATE POLICY catalog_authority_allow ON forge.membership_roles TO forge_catalog_authority
    USING (organization_id=forge.context_organization() AND role='organization_admin')
    WITH CHECK (false);
CREATE POLICY catalog_authority_limit ON forge.membership_roles AS RESTRICTIVE
    TO forge_catalog_authority
    USING (organization_id=forge.context_organization() AND role='organization_admin')
    WITH CHECK (false);

CREATE FUNCTION forge.lock_catalog_authority(
    requested_org uuid, requested_member uuid, tenant uuid, object_id uuid
) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
    enabled boolean;
    member_identity uuid;
    member_status text;
    member_revision bigint;
BEGIN
    IF requested_org IS NULL OR requested_member IS NULL OR tenant IS NULL
        OR object_id IS NULL OR requested_org IS DISTINCT FROM forge.context_organization()
        OR current_setting('forge.provider',true) IS DISTINCT FROM 'entra'
        OR current_setting('forge.issuer',true) IS DISTINCT FROM
            'https://login.microsoftonline.com/' || tenant::text || '/v2.0'
        OR current_setting('forge.subject',true) IS DISTINCT FROM object_id::text THEN
        RETURN NULL;
    END IF;
    -- Fixed order: org -> member -> identity -> grant; caller next locks operation/pointer.
    SELECT active INTO enabled FROM forge.organizations
        WHERE id=requested_org FOR UPDATE;
    IF NOT FOUND OR NOT enabled THEN RETURN NULL; END IF;
    SELECT identity_id,status,revision INTO member_identity,member_status,member_revision
        FROM forge.memberships WHERE organization_id=requested_org AND id=requested_member
        FOR UPDATE;
    IF NOT FOUND OR member_status<>'active' THEN RETURN NULL; END IF;
    PERFORM 1 FROM forge.identities WHERE id=member_identity AND provider='entra'
        AND entra_tenant_id=tenant AND entra_object_id=object_id
        AND issuer='https://login.microsoftonline.com/' || tenant::text || '/v2.0'
        AND subject=object_id::text FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    PERFORM 1 FROM forge.membership_roles WHERE organization_id=requested_org
        AND membership_id=requested_member AND role='organization_admin' FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    RETURN member_revision;
END $$;
REVOKE ALL ON FUNCTION forge.lock_catalog_authority(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.lock_catalog_authority(uuid,uuid,uuid,uuid)
    TO forge_config_publisher;

ALTER TABLE forge.model_catalog_snapshots ADD CONSTRAINT catalog_replay_snapshot
    UNIQUE (organization_id,router_binding_id,revision,payload_sha256);
ALTER TABLE forge.outbox_events ADD CONSTRAINT catalog_replay_event
    UNIQUE (event_id,organization_id,actor_id,request_id,resource_id,
        previous_revision,revision,event_type);
CREATE TABLE forge.catalog_publication_operations (
    operation_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    router_binding_id uuid NOT NULL,
    expected_revision bigint NOT NULL CHECK (expected_revision>=0
        AND expected_revision<9223372036854775807),
    catalog_revision bigint NOT NULL CHECK (catalog_revision=expected_revision+1),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    event_id uuid NOT NULL UNIQUE,
    event_type text NOT NULL DEFAULT 'model_catalog.published'
        CHECK (event_type='model_catalog.published'),
    FOREIGN KEY (organization_id,actor_id)
        REFERENCES forge.memberships(organization_id,id),
    FOREIGN KEY (organization_id,router_binding_id,catalog_revision,payload_sha256)
        REFERENCES forge.model_catalog_snapshots(organization_id,router_binding_id,revision,payload_sha256),
    FOREIGN KEY (event_id,organization_id,actor_id,operation_id,router_binding_id,
            expected_revision,catalog_revision,event_type)
        REFERENCES forge.outbox_events(event_id,organization_id,actor_id,request_id,
            resource_id,previous_revision,revision,event_type)
);
ALTER TABLE forge.catalog_publication_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.catalog_publication_operations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.catalog_publication_operations FROM PUBLIC;
GRANT SELECT,INSERT ON forge.catalog_publication_operations TO forge_config_publisher;
CREATE POLICY catalog_operation_read ON forge.catalog_publication_operations
    FOR SELECT TO forge_config_publisher USING (organization_id=forge.context_organization());
CREATE POLICY catalog_operation_insert ON forge.catalog_publication_operations
    FOR INSERT TO forge_config_publisher WITH CHECK (organization_id=forge.context_organization());
RESET ROLE;
-- The helper owner cannot log in, inherit, bypass RLS or own any authority table.
ALTER FUNCTION forge.lock_catalog_authority(uuid,uuid,uuid,uuid)
    OWNER TO forge_catalog_authority;
COMMIT;
