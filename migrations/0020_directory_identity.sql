-- Additive directory identity: the server-discovered "me" context.
-- Never applied to an existing demo implicitly. Own NOLOGIN authority with narrow RLS
-- policies; the only caller is the existing forge_gateway_service function pool.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_directory_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_directory_authority;
-- Column grant: the password hash is never readable by this authority.
GRANT SELECT(id,canonical_email,display_name) ON forge.owned_accounts TO forge_directory_authority;
-- identities: the existing PUBLIC membership policy consults it, so the authority needs a
-- (self-only) read path, exactly like the enrollment authority.
GRANT SELECT(id) ON forge.identities TO forge_directory_authority;
GRANT SELECT ON forge.organizations,forge.memberships,forge.membership_roles,
 forge.membership_departments,forge.departments TO forge_directory_authority;

-- Account scope: every row visible to the authority belongs to the validated account,
-- which the SECURITY DEFINER function sets transaction-locally after session validation.
CREATE POLICY directory_scope ON forge.identities FOR SELECT TO forge_directory_authority
 USING(id=forge.enrollment_uuid('forge.directory_account'));
CREATE POLICY directory_scope ON forge.owned_accounts FOR SELECT TO forge_directory_authority
 USING(id=forge.enrollment_uuid('forge.directory_account'));
CREATE POLICY directory_scope ON forge.memberships FOR SELECT TO forge_directory_authority
 USING(identity_id=forge.enrollment_uuid('forge.directory_account'));
CREATE POLICY directory_scope ON forge.organizations FOR SELECT TO forge_directory_authority
 USING(id IN (SELECT m.organization_id FROM forge.memberships m
  WHERE m.identity_id=forge.enrollment_uuid('forge.directory_account')));
CREATE POLICY directory_scope ON forge.membership_roles FOR SELECT TO forge_directory_authority
 USING(EXISTS(SELECT 1 FROM forge.memberships m
  WHERE m.organization_id=membership_roles.organization_id AND m.id=membership_roles.membership_id
   AND m.identity_id=forge.enrollment_uuid('forge.directory_account')));
CREATE POLICY directory_scope ON forge.membership_departments FOR SELECT TO forge_directory_authority
 USING(EXISTS(SELECT 1 FROM forge.memberships m
  WHERE m.organization_id=membership_departments.organization_id AND m.id=membership_departments.membership_id
   AND m.identity_id=forge.enrollment_uuid('forge.directory_account')));
-- Departments: only the ones the validated account's own memberships belong to.
CREATE POLICY directory_read ON forge.departments FOR SELECT TO forge_directory_authority
 USING(EXISTS(SELECT 1 FROM forge.membership_departments md
  WHERE md.organization_id=departments.organization_id AND md.department_id=departments.id));
RESET ROLE;

GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),forge.account_validate_session(text)
 TO forge_directory_authority;
GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;

CREATE FUNCTION forge.directory_account(digest text) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_DENIED';
 END IF;
 PERFORM set_config('forge.directory_account',account::text,true);
 RETURN account;
END $$;

CREATE FUNCTION forge.directory_me(digest text)
RETURNS TABLE(account_id uuid,email text,display_name text,org_id uuid,org_name text,
 member_status text,member_roles text[],member_departments jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.directory_account(digest);
 RETURN QUERY SELECT a.id,a.canonical_email,a.display_name,o.id,o.display_name,m.status,
  coalesce((SELECT array_agg(r.role ORDER BY r.role) FROM forge.membership_roles r
   WHERE r.organization_id=m.organization_id AND r.membership_id=m.id),ARRAY[]::text[]),
  coalesce((SELECT jsonb_agg(jsonb_build_object('id',d.id,'name',d.name) ORDER BY d.name,d.id)
   FROM forge.membership_departments md JOIN forge.departments d
    ON d.organization_id=md.organization_id AND d.id=md.department_id AND d.active
   WHERE md.organization_id=m.organization_id AND md.membership_id=m.id),'[]'::jsonb)
  FROM forge.owned_accounts a JOIN forge.memberships m ON m.identity_id=a.id
  JOIN forge.organizations o ON o.id=m.organization_id AND o.active
  WHERE a.id=account ORDER BY o.display_name,o.id;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.directory_account(text),forge.directory_me(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.directory_me(text) TO forge_gateway_service;
COMMIT;
