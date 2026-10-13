-- Member department assignment. Additive and forward-only.
-- * ``directory_member_department`` lets an administrator of a company make ONE active department of that company the member's
--   department: the member's other department links of this company are removed and the chosen one is kept (idempotent). It
--   re-validates the live session and the administrator (``directory_admin``), requires the member to be an active or suspended
--   member of exactly that company and the department to be an active department of exactly that company. A stranger, a member,
--   another company's administrator, an unknown or foreign member or department and a stale session are the same
--   ``DIRECTORY_DENIED``; a missing argument is ``DIRECTORY_INVALID``.
-- * The authority gains INSERT and DELETE on the link table only while ``forge.directory_org`` is pinned to that company by the
--   function; it still cannot touch departments, roles or the status of a member through this path.
-- * The member row is locked first, so two concurrent assignments of one member are serialized and the last one wins whole.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
GRANT INSERT,DELETE ON forge.membership_departments TO forge_directory_authority;
CREATE POLICY directory_assign_insert ON forge.membership_departments FOR INSERT TO forge_directory_authority
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.directory_org'));
CREATE POLICY directory_assign_delete ON forge.membership_departments FOR DELETE TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org'));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;
CREATE FUNCTION forge.directory_member_department(digest text,org uuid,target_member uuid,target_department uuid)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,member_roles text[],member_departments jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.directory_admin(digest,org);
 IF target_member IS NULL OR target_department IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_INVALID';
 END IF;
 PERFORM 1 FROM forge.memberships m WHERE m.organization_id=org AND m.id=target_member AND m.status IN ('active','suspended') FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_DENIED'; END IF;
 PERFORM 1 FROM forge.departments d WHERE d.organization_id=org AND d.id=target_department AND d.active;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_DENIED'; END IF;
 DELETE FROM forge.membership_departments md
  WHERE md.organization_id=org AND md.membership_id=target_member AND md.department_id<>target_department;
 INSERT INTO forge.membership_departments(organization_id,membership_id,department_id)
  VALUES(org,target_member,target_department) ON CONFLICT DO NOTHING;
 RETURN QUERY SELECT * FROM forge.directory_member_rows(org,target_member);
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.directory_member_department(text,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.directory_member_department(text,uuid,uuid,uuid) TO forge_gateway_service;
COMMIT;
