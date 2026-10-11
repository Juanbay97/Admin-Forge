-- Additive member directory: admin-only list of an organization's members.
-- Builds on the 0020/0021 directory authority; never applied to an existing demo implicitly.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
-- Once an administrator check has pinned forge.directory_org inside the transaction,
-- the organization's member rows become readable (and nothing outside it).
CREATE POLICY directory_org_read ON forge.memberships FOR SELECT TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org'));
CREATE POLICY directory_org_read ON forge.membership_roles FOR SELECT TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org'));
CREATE POLICY directory_org_read ON forge.membership_departments FOR SELECT TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org'));
CREATE POLICY directory_org_read ON forge.owned_accounts FOR SELECT TO forge_directory_authority
 USING(EXISTS(SELECT 1 FROM forge.memberships m
  WHERE m.identity_id=owned_accounts.id AND m.organization_id=forge.enrollment_uuid('forge.directory_org')));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;

-- Internal row builder: not callable by the service pool, only by the functions that
-- already pinned an administrator context. only_member NULL means the whole organization.
CREATE FUNCTION forge.directory_member_rows(org uuid,only_member uuid)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,
 member_roles text[],member_departments jsonb)
LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT m.id,a.canonical_email,a.display_name,m.status,
  coalesce((SELECT array_agg(r.role ORDER BY r.role) FROM forge.membership_roles r
   WHERE r.organization_id=m.organization_id AND r.membership_id=m.id),ARRAY[]::text[]),
  coalesce((SELECT jsonb_agg(jsonb_build_object('id',d.id,'name',d.name) ORDER BY d.name,d.id)
   FROM forge.membership_departments md JOIN forge.departments d
    ON d.organization_id=md.organization_id AND d.id=md.department_id AND d.active
   WHERE md.organization_id=m.organization_id AND md.membership_id=m.id),'[]'::jsonb)
 FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id
 WHERE m.organization_id=org AND m.status IN ('active','suspended')
  AND (only_member IS NULL OR m.id=only_member)
 ORDER BY lower(a.canonical_email),m.id
$$;

CREATE FUNCTION forge.directory_members(digest text,org uuid)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,
 member_roles text[],member_departments jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.directory_admin(digest,org);
 RETURN QUERY SELECT * FROM forge.directory_member_rows(org,NULL);
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.directory_member_rows(uuid,uuid),forge.directory_members(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.directory_members(text,uuid) TO forge_gateway_service;
COMMIT;
