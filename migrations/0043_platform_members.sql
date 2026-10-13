-- Platform company members. Additive and forward-only.
-- * ``platform_company_members`` lets a fresh verified platform owner read the members of ONE company: the same directory fields a
--   company administrator already has (email, name, status, roles, active departments), suspended members included, as a keyset
--   page ordered by membership id (at most 100 per page). An unknown company is ``PLATFORM_NOT_FOUND``; a company administrator, a
--   stale digest and an unverified owner are denied as everywhere else on the platform surface.
-- * The authority sees those rows only while the function has pinned ``forge.organization`` (one company at a time): the policies
--   below are the same shape as the directory authority's, scoped to the platform authority. The password hash column is never
--   granted (a column grant on ``owned_accounts``), and no login role gains a table privilege.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
GRANT SELECT(id,canonical_email,display_name) ON forge.owned_accounts TO forge_platform_authority;
GRANT SELECT ON forge.membership_roles,forge.membership_departments,forge.departments TO forge_platform_authority;
CREATE POLICY platform_company_members ON forge.memberships FOR SELECT TO forge_platform_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_company_members ON forge.membership_roles FOR SELECT TO forge_platform_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_company_members ON forge.membership_departments FOR SELECT TO forge_platform_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_company_members ON forge.departments FOR SELECT TO forge_platform_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_company_members ON forge.owned_accounts FOR SELECT TO forge_platform_authority
 USING(EXISTS(SELECT 1 FROM forge.memberships m
  WHERE m.identity_id=owned_accounts.id AND m.organization_id=forge.enrollment_uuid('forge.organization')));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;
CREATE FUNCTION forge.platform_company_members(digest text,org uuid,after_member uuid,page integer)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,member_roles text[],member_departments jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 IF page IS NULL OR page NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 IF org IS NOT NULL THEN PERFORM set_config('forge.organization',org::text,true); END IF;
 PERFORM 1 FROM forge.organizations o WHERE org IS NOT NULL AND o.id=org;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND'; END IF;
 RETURN QUERY SELECT m.id,a.canonical_email,a.display_name,m.status,
   coalesce((SELECT array_agg(r.role ORDER BY r.role) FROM forge.membership_roles r
    WHERE r.organization_id=m.organization_id AND r.membership_id=m.id),ARRAY[]::text[]),
   coalesce((SELECT jsonb_agg(jsonb_build_object('id',d.id,'name',d.name) ORDER BY d.name,d.id)
    FROM forge.membership_departments md JOIN forge.departments d
     ON d.organization_id=md.organization_id AND d.id=md.department_id AND d.active
    WHERE md.organization_id=m.organization_id AND md.membership_id=m.id),'[]'::jsonb)
  FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id
  WHERE m.organization_id=org AND m.status IN ('active','suspended') AND (after_member IS NULL OR m.id>after_member)
  ORDER BY m.id LIMIT page;
 PERFORM set_config('forge.organization','',true);
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_company_members(text,uuid,uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_company_members(text,uuid,uuid,integer) TO forge_platform_service;
COMMIT;
