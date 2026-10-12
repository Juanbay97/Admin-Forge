-- Scoped session revocation: suspending one membership revokes the account's sessions only
-- when the account has no other active membership. Sessions are account-scoped, so revoking
-- them for a multi-organization member would log them out of organizations that never
-- suspended them; the suspended organization is denied per request instead.
-- Forward-only and additive: only the body of forge.directory_member_status changes, no new
-- table, column, grant or policy. The existing directory_scope policy lets the authority read
-- the memberships of the one account the function pins as the target.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';

GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;

CREATE OR REPLACE FUNCTION forge.directory_member_status(digest text,org uuid,target_member uuid,target_state text)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,
 member_roles text[],member_departments jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE target_identity uuid; previous_state text; remaining integer; other_active integer;
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
  IF target_state='suspended' THEN
   -- Two organizations may suspend the same account at once; serialize per account so the
   -- second one sees the first one's commit and the last active membership still revokes.
   PERFORM pg_advisory_xact_lock(hashtextextended(target_identity::text,0));
  END IF;
  UPDATE forge.memberships SET status=target_state WHERE organization_id=org AND id=target_member;
  IF target_state='suspended' THEN
   -- Pin the target account: its memberships in other organizations become readable (existing
   -- directory_scope policy) and its sessions revocable (existing directory_session_* policies).
   PERFORM set_config('forge.directory_account',target_identity::text,true);
   PERFORM set_config('forge.directory_target',target_identity::text,true);
   SELECT count(*) INTO other_active FROM forge.memberships m
    WHERE m.identity_id=target_identity AND m.status='active';
   -- Sessions are account-scoped: revoke them only when nothing else keeps the account active.
   IF other_active=0 THEN
    UPDATE forge.account_sessions SET revoked=true WHERE account_id=target_identity AND NOT revoked;
   END IF;
  END IF;
 END IF;
 RETURN QUERY SELECT * FROM forge.directory_member_rows(org,target_member);
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.directory_member_status(text,uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.directory_member_status(text,uuid,uuid,text) TO forge_gateway_service;
COMMIT;
