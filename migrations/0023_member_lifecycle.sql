-- Additive member lifecycle: admin-only suspend and reactivate with a last-admin guard.
-- Builds on the 0020-0022 directory authority; never applied to an existing demo implicitly.
-- The guard and every role check live inside the function, behind row locks, so
-- concurrent suspensions cannot empty an organization of administrators.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
-- Status is the only membership column this authority may ever change.
GRANT UPDATE(status) ON forge.memberships TO forge_directory_authority;
-- Sessions: the digest is never readable; only revocation of the targeted account is possible.
GRANT SELECT(account_id,revoked),UPDATE(revoked) ON forge.account_sessions TO forge_directory_authority;

CREATE POLICY directory_member_update ON forge.memberships FOR UPDATE TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org') AND status IN ('active','suspended'))
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.directory_org') AND status IN ('active','suspended'));
-- Sessions are reachable only for the single account the function pinned as the target.
CREATE POLICY directory_session_read ON forge.account_sessions FOR SELECT TO forge_directory_authority
 USING(account_id=forge.enrollment_uuid('forge.directory_target'));
CREATE POLICY directory_session_revoke ON forge.account_sessions FOR UPDATE TO forge_directory_authority
 USING(account_id=forge.enrollment_uuid('forge.directory_target'))
 WITH CHECK(account_id=forge.enrollment_uuid('forge.directory_target') AND revoked);
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;

CREATE FUNCTION forge.directory_member_status(digest text,org uuid,target_member uuid,target_state text)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,
 member_roles text[],member_departments jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE target_identity uuid; previous_state text; remaining integer;
BEGIN
 IF target_state IS NULL OR target_state NOT IN ('active','suspended') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_INVALID';
 END IF;
 PERFORM forge.directory_admin(digest,org);
 -- Serialize every change to this organization's administrator set: lock all administrator
 -- memberships in a fixed order (their role rows never change here, so the set is stable).
 PERFORM 1 FROM forge.memberships m WHERE m.organization_id=org AND EXISTS(
   SELECT 1 FROM forge.membership_roles r WHERE r.organization_id=m.organization_id
    AND r.membership_id=m.id AND r.role='organization_admin')
  ORDER BY m.id FOR UPDATE OF m;
 -- A new statement sees any commit that released the lock: the actor must still qualify.
 PERFORM forge.directory_admin(digest,org);
 SELECT m.identity_id,m.status INTO target_identity,previous_state FROM forge.memberships m
  WHERE m.organization_id=org AND m.id=target_member AND m.status IN ('active','suspended') FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_DENIED';
 END IF;
 IF previous_state<>target_state THEN
  IF target_state='suspended' AND EXISTS(SELECT 1 FROM forge.membership_roles r
    WHERE r.organization_id=org AND r.membership_id=target_member AND r.role='organization_admin') THEN
   SELECT count(*) INTO remaining FROM forge.memberships m
    WHERE m.organization_id=org AND m.id<>target_member AND m.status='active' AND EXISTS(
     SELECT 1 FROM forge.membership_roles r WHERE r.organization_id=m.organization_id
      AND r.membership_id=m.id AND r.role='organization_admin');
   IF remaining=0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_LAST_ADMIN';
   END IF;
  END IF;
  UPDATE forge.memberships SET status=target_state WHERE organization_id=org AND id=target_member;
  IF target_state='suspended' THEN
   -- Suspension revokes the member's live sessions so nothing in flight can continue.
   PERFORM set_config('forge.directory_target',target_identity::text,true);
   UPDATE forge.account_sessions SET revoked=true WHERE account_id=target_identity AND NOT revoked;
  END IF;
 END IF;
 RETURN QUERY SELECT * FROM forge.directory_member_rows(org,target_member);
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.directory_member_status(text,uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.directory_member_status(text,uuid,uuid,text) TO forge_gateway_service;
COMMIT;
