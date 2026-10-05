-- Additive authorization metadata; trusted administrator, dedicated Forge DB.
-- No roles/admins seeded, mutation API, LOGIN provisioning or migration runner.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
SET LOCAL ROLE forge_migrator;

ALTER TABLE forge.memberships
    ADD COLUMN revision bigint NOT NULL DEFAULT 1,
    ADD CONSTRAINT membership_revision_positive CHECK (revision > 0);

CREATE TABLE forge.membership_roles (
    organization_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    role text NOT NULL,
    CONSTRAINT membership_roles_primary PRIMARY KEY (organization_id, membership_id, role),
    CONSTRAINT membership_roles_membership FOREIGN KEY (organization_id, membership_id)
        REFERENCES forge.memberships(organization_id, id),
    CONSTRAINT membership_roles_known CHECK (
        role IN ('organization_admin', 'department_manager', 'skill_reviewer', 'member'))
);
REVOKE ALL ON forge.membership_roles FROM PUBLIC, forge_identity_binder;
GRANT SELECT ON forge.membership_roles TO forge_runtime;
ALTER TABLE forge.membership_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.membership_roles FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_role_scope ON forge.membership_roles
    FOR SELECT TO forge_runtime
    USING (
        organization_id = forge.context_organization()
        AND EXISTS (
            SELECT 1 FROM forge.memberships AS m
            JOIN forge.organizations AS o ON o.id = m.organization_id
            JOIN forge.identities AS i ON i.id = m.identity_id
            WHERE m.organization_id = membership_roles.organization_id
              AND m.id = membership_roles.membership_id
              AND m.status = 'active' AND o.active
              AND (i.provider <> 'entra' OR (
                  i.entra_tenant_id IS NOT NULL AND i.entra_object_id IS NOT NULL
                  AND i.issuer = 'https://login.microsoftonline.com/' || i.entra_tenant_id::text || '/v2.0'
                  AND i.subject = i.entra_object_id::text
              ))
        )
    );
COMMIT;
