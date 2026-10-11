-- Additive department directory: admin-only list/create with unique names per organization.
-- Builds on the 0020 directory authority; never applied to an existing demo implicitly.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
GRANT INSERT ON forge.departments TO forge_directory_authority;
-- Names are unique per organization (case/space-insensitive); also closes the create race.
-- Pre-existing duplicates abort this migration atomically instead of being rewritten.
CREATE UNIQUE INDEX departments_name_unique ON forge.departments(organization_id,lower(btrim(name)));
-- Once an administrator check has pinned forge.directory_org inside the transaction,
-- the whole organization becomes readable and insertable (and nothing else).
CREATE POLICY directory_org_read ON forge.departments FOR SELECT TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org'));
CREATE POLICY directory_write ON forge.departments FOR INSERT TO forge_directory_authority
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.directory_org') AND active AND revision=1);
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;

-- Live session + active administrator of an active organization, else the uniform denial.
CREATE FUNCTION forge.directory_admin(digest text,org uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.directory_account(digest);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.memberships m
   JOIN forge.organizations o ON o.id=m.organization_id AND o.active
   JOIN forge.membership_roles r ON r.organization_id=m.organization_id AND r.membership_id=m.id
    AND r.role='organization_admin'
  WHERE m.organization_id=org AND m.identity_id=account AND m.status='active') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_DENIED';
 END IF;
 PERFORM set_config('forge.directory_org',org::text,true);
 RETURN account;
END $$;

CREATE FUNCTION forge.directory_departments(digest text,org uuid)
RETURNS TABLE(department_id uuid,department_name text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.directory_admin(digest,org);
 RETURN QUERY SELECT d.id,d.name FROM forge.departments d
  WHERE d.organization_id=org AND d.active ORDER BY d.name,d.id;
END $$;

CREATE FUNCTION forge.directory_department_create(digest text,org uuid,department_label text)
RETURNS TABLE(department_id uuid,department_name text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE created uuid;
BEGIN
 PERFORM forge.directory_admin(digest,org);
 IF department_label IS NULL OR length(btrim(department_label)) NOT BETWEEN 1 AND 120 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_INVALID';
 END IF;
 BEGIN
  INSERT INTO forge.departments(organization_id,id,name) VALUES(org,gen_random_uuid(),btrim(department_label))
   RETURNING id INTO created;
 EXCEPTION WHEN unique_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_CONFLICT';
 END;
 RETURN QUERY SELECT d.id,d.name FROM forge.departments d WHERE d.organization_id=org AND d.id=created;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.directory_admin(text,uuid),forge.directory_departments(text,uuid),
 forge.directory_department_create(text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.directory_departments(text,uuid),
 forge.directory_department_create(text,uuid,text) TO forge_gateway_service;
COMMIT;
