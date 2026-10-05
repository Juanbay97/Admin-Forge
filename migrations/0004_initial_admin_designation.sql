-- Initial-only central designation. Trusted deployment owns LOGIN/pool configuration.
-- No self-registration, organization activation, recovery or audit publication.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
CREATE ROLE forge_designator NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_designator',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
CREATE TABLE forge.initial_admin_designations (
    organization_id uuid PRIMARY KEY REFERENCES forge.organizations(id),
    membership_id uuid NOT NULL,
    request_id uuid NOT NULL UNIQUE,
    actor_id uuid NOT NULL,
    target_tenant_id uuid NOT NULL,
    expected_revision bigint NOT NULL CHECK (expected_revision>0 AND expected_revision<9223372036854775807),
    revision bigint NOT NULL CHECK (revision=expected_revision+1),
    event_id uuid NOT NULL UNIQUE,
    CONSTRAINT designation_member FOREIGN KEY (organization_id,membership_id)
        REFERENCES forge.memberships(organization_id,id),
    CONSTRAINT designation_event_payload UNIQUE
        (organization_id,request_id,event_id,actor_id,membership_id,expected_revision,revision)
);
CREATE TABLE forge.initial_admin_outbox (
    event_id uuid PRIMARY KEY,
    schema_version integer NOT NULL CHECK (schema_version=1),
    organization_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    actor_type text NOT NULL CHECK (actor_type='deployment_operator'),
    source text NOT NULL CHECK (source='server'),
    event_type text NOT NULL CHECK (event_type='membership.initial_admin_designated'),
    occurred_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    received_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    request_id uuid NOT NULL UNIQUE,
    resource_type text NOT NULL CHECK (resource_type='membership'),
    resource_id uuid NOT NULL,
    outcome text NOT NULL CHECK (outcome='succeeded'),
    previous_revision bigint NOT NULL,
    revision bigint NOT NULL,
    metadata jsonb NOT NULL CHECK (metadata=jsonb_build_object('role','organization_admin',
        'previous_revision',previous_revision,'revision',revision)),
    CONSTRAINT designation_event_record FOREIGN KEY
        (organization_id,request_id,event_id,actor_id,resource_id,previous_revision,revision)
        REFERENCES forge.initial_admin_designations
        (organization_id,request_id,event_id,actor_id,membership_id,expected_revision,revision)
);
ALTER TABLE forge.initial_admin_designations ADD CONSTRAINT designation_committed_event
    FOREIGN KEY (event_id) REFERENCES forge.initial_admin_outbox(event_id)
    DEFERRABLE INITIALLY DEFERRED;
REVOKE ALL ON forge.initial_admin_designations,forge.initial_admin_outbox
    FROM PUBLIC,forge_runtime,forge_identity_binder;
GRANT USAGE ON SCHEMA forge TO forge_designator;
GRANT SELECT ON forge.identities,forge.organizations,forge.memberships,forge.membership_roles
    TO forge_designator;
GRANT UPDATE(revision) ON forge.memberships TO forge_designator;
GRANT INSERT ON forge.membership_roles TO forge_designator;
GRANT SELECT,INSERT ON forge.initial_admin_designations,forge.initial_admin_outbox TO forge_designator;
ALTER TABLE forge.initial_admin_designations ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.initial_admin_designations FORCE ROW LEVEL SECURITY;
ALTER TABLE forge.initial_admin_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.initial_admin_outbox FORCE ROW LEVEL SECURITY;
-- Existing PUBLIC policy evaluation needs these invokers, not owner authority.
GRANT EXECUTE ON FUNCTION forge.context_organization(),forge.context_ready(),
    forge.has_membership(uuid) TO forge_designator;

CREATE FUNCTION forge.designation_uuid(key text) RETURNS uuid
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT CASE WHEN key IN ('organization','member','identity','actor','request')
        AND current_setting('forge.designation_' || key, true) ~
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('forge.designation_' || key, true)::uuid ELSE NULL END
$$;
REVOKE ALL ON FUNCTION forge.designation_uuid(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.designation_uuid(text) TO forge_designator;

CREATE FUNCTION forge.designation_scope(organization uuid,member uuid,actor uuid,request uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT organization = forge.designation_uuid('organization')
        AND (member IS NULL OR member = forge.designation_uuid('member'))
        AND (actor IS NULL OR actor = forge.designation_uuid('actor'))
        AND (request IS NULL OR request = forge.designation_uuid('request'))
$$;
REVOKE ALL ON FUNCTION forge.designation_scope(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.designation_scope(uuid,uuid,uuid,uuid) TO forge_designator;

CREATE FUNCTION forge.designation_bound_member(organization uuid,member uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT EXISTS (SELECT 1 FROM forge.memberships AS m
        JOIN forge.identities AS i ON i.id=m.identity_id
        WHERE m.organization_id=organization AND m.id=member AND m.status='active'
          AND i.provider='entra' AND i.entra_tenant_id IS NOT NULL
          AND i.entra_object_id IS NOT NULL
          AND i.issuer='https://login.microsoftonline.com/' || i.entra_tenant_id::text || '/v2.0'
          AND i.subject=i.entra_object_id::text)
$$;
REVOKE ALL ON FUNCTION forge.designation_bound_member(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.designation_bound_member(uuid,uuid) TO forge_designator;

CREATE POLICY designation_identity ON forge.identities
    FOR SELECT TO forge_designator
    USING (id = forge.designation_uuid('identity') AND provider='entra' AND entra_tenant_id IS NOT NULL AND entra_object_id IS NOT NULL AND issuer='https://login.microsoftonline.com/' || entra_tenant_id::text || '/v2.0' AND subject=entra_object_id::text);

CREATE POLICY designation_org_allow ON forge.organizations
    FOR SELECT TO forge_designator
    USING (forge.designation_scope(id,NULL,NULL,NULL));

CREATE POLICY designation_org_limit ON forge.organizations AS RESTRICTIVE
    FOR SELECT TO forge_designator
    USING (forge.designation_scope(id,NULL,NULL,NULL));

CREATE POLICY designation_member_allow ON forge.memberships
    FOR SELECT TO forge_designator
    USING (forge.designation_scope(organization_id,id,NULL,NULL) AND status='active');

CREATE POLICY designation_member_limit ON forge.memberships AS RESTRICTIVE
    FOR ALL TO forge_designator
    USING (forge.designation_scope(organization_id,id,NULL,NULL) AND status='active')
    WITH CHECK (forge.designation_scope(organization_id,id,NULL,NULL) AND status='active');

CREATE POLICY designation_revision ON forge.memberships
    FOR UPDATE TO forge_designator
    USING (forge.designation_scope(organization_id,id,NULL,NULL) AND status='active')
    WITH CHECK (forge.designation_scope(organization_id,id,NULL,NULL) AND status='active' AND forge.designation_bound_member(organization_id,id));

CREATE POLICY designation_admin_read ON forge.membership_roles
    FOR SELECT TO forge_designator
    USING (forge.designation_scope(organization_id,NULL,NULL,NULL) AND role='organization_admin');

CREATE POLICY designation_admin_insert ON forge.membership_roles
    FOR INSERT TO forge_designator

    WITH CHECK (forge.designation_scope(organization_id,membership_id,NULL,NULL) AND role='organization_admin' AND forge.designation_bound_member(organization_id,membership_id));

CREATE POLICY designation_record_read ON forge.initial_admin_designations
    FOR SELECT TO forge_designator
    USING (forge.designation_scope(organization_id,membership_id,actor_id,request_id));

CREATE POLICY designation_record_insert ON forge.initial_admin_designations
    FOR INSERT TO forge_designator

    WITH CHECK (forge.designation_scope(organization_id,membership_id,actor_id,request_id));

CREATE POLICY designation_event_read ON forge.initial_admin_outbox
    FOR SELECT TO forge_designator
    USING (forge.designation_scope(organization_id,resource_id,actor_id,request_id));

CREATE POLICY designation_event_insert ON forge.initial_admin_outbox
    FOR INSERT TO forge_designator

    WITH CHECK (forge.designation_scope(organization_id,resource_id,actor_id,request_id));
COMMIT;
