-- One-shot bootstrap migration, run by a trusted database administrator.
-- Credentials and LOGIN provisioning belong to deployment, not this migration.
BEGIN;
CREATE ROLE forge_migrator NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_runtime', current_database());
END $$;
CREATE SCHEMA forge AUTHORIZATION forge_migrator;
SET LOCAL ROLE forge_migrator;
CREATE TABLE forge.identities (
    id uuid PRIMARY KEY,
    provider text NOT NULL CHECK (btrim(provider) <> ''),
    issuer text NOT NULL CHECK (btrim(issuer) <> ''),
    subject text NOT NULL CHECK (btrim(subject) <> ''),
    UNIQUE (provider, issuer, subject)
);
CREATE TABLE forge.organizations (
    id uuid PRIMARY KEY,
    slug text NOT NULL UNIQUE CHECK (btrim(slug) <> ''),
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    active boolean NOT NULL DEFAULT true,
    selected_config_revision bigint NOT NULL CHECK (selected_config_revision > 0)
);
CREATE TABLE forge.memberships (
    organization_id uuid NOT NULL REFERENCES forge.organizations(id),
    id uuid NOT NULL,
    identity_id uuid NOT NULL REFERENCES forge.identities(id),
    status text NOT NULL CHECK (status IN ('active', 'suspended', 'archived')),
    PRIMARY KEY (organization_id, id),
    UNIQUE (organization_id, identity_id)
);
CREATE TABLE forge.configuration_revisions (
    organization_id uuid NOT NULL REFERENCES forge.organizations(id),
    revision bigint NOT NULL CHECK (revision > 0),
    PRIMARY KEY (organization_id, revision)
);
ALTER TABLE forge.organizations ADD CONSTRAINT selected_configuration
    FOREIGN KEY (id, selected_config_revision)
    REFERENCES forge.configuration_revisions(organization_id, revision)
    DEFERRABLE INITIALLY DEFERRED;
GRANT USAGE ON SCHEMA forge TO forge_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA forge TO forge_runtime;
-- Helpers never run with owner's privileges. An organization string is parsed
-- defensively so missing, blank or malformed context cannot expose data/errors.
ALTER DEFAULT PRIVILEGES IN SCHEMA forge REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE FUNCTION forge.context_organization() RETURNS uuid
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog AS $$
    SELECT CASE WHEN current_setting('forge.organization', true) ~
        '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        THEN current_setting('forge.organization', true)::uuid ELSE NULL END
$$;
CREATE FUNCTION forge.context_ready() RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog AS $$
    SELECT forge.context_organization() IS NOT NULL
        AND nullif(btrim(current_setting('forge.provider', true)), '') IS NOT NULL
        AND nullif(btrim(current_setting('forge.issuer', true)), '') IS NOT NULL
        AND nullif(btrim(current_setting('forge.subject', true)), '') IS NOT NULL
$$;
-- This invoker query sees memberships through their own RLS; that policy only
-- consults identities, whose self-only policy never consults memberships.
CREATE FUNCTION forge.has_membership(target uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog AS $$
    SELECT EXISTS (SELECT 1 FROM forge.memberships WHERE organization_id = target)
$$;
GRANT EXECUTE ON FUNCTION forge.context_organization(), forge.context_ready(),
    forge.has_membership(uuid) TO forge_runtime;

ALTER TABLE forge.identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.identities FORCE ROW LEVEL SECURITY;
CREATE POLICY identity_scope ON forge.identities FOR ALL
USING (
    forge.context_ready()
    AND provider = current_setting('forge.provider', true)
    AND issuer = current_setting('forge.issuer', true)
    AND subject = current_setting('forge.subject', true)
)
WITH CHECK (
    forge.context_ready()
    AND provider = current_setting('forge.provider', true)
    AND issuer = current_setting('forge.issuer', true)
    AND subject = current_setting('forge.subject', true)
);

ALTER TABLE forge.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_scope ON forge.memberships FOR ALL
USING (
    organization_id = forge.context_organization()
    AND status IN ('active', 'suspended')
    AND EXISTS (SELECT 1 FROM forge.identities WHERE id = identity_id)
)
WITH CHECK (
    organization_id = forge.context_organization()
    AND status IN ('active', 'suspended')
    AND EXISTS (SELECT 1 FROM forge.identities WHERE id = identity_id)
);

ALTER TABLE forge.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY organization_scope ON forge.organizations FOR ALL
USING (id = forge.context_organization() AND forge.has_membership(id))
WITH CHECK (id = forge.context_organization() AND forge.has_membership(id));

ALTER TABLE forge.configuration_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.configuration_revisions FORCE ROW LEVEL SECURITY;
CREATE POLICY configuration_scope ON forge.configuration_revisions FOR ALL
USING (
    organization_id = forge.context_organization()
    AND forge.has_membership(organization_id)
)
WITH CHECK (
    organization_id = forge.context_organization()
    AND forge.has_membership(organization_id)
);
-- Context is supplied by trusted server code. RLS does not stop malicious app
-- SQL from overwriting its own custom GUCs, and FK diagnostics remain private.
COMMIT;
