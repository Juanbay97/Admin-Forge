-- Invitation preview. Additive and forward-only.
-- * ``account_invitation_preview`` lets the holder of an invitation's private link (the invitation id plus the capability's digest) learn
--   the email address and display name the invitation was issued for, WITHOUT consuming anything: the join page can then show who is
--   joining and sign the person in after the (pinned, unchanged) accept call without asking for the address again.
-- * It answers only for a pending, unexpired invitation of an ACTIVE company. An unknown identifier, a wrong capability, an expired, used or
--   withdrawn invitation and a suspended company are the same ``INVITATION_DENIED``, so a caller learns nothing about which case it was
--   and cannot enumerate invitations (the capability is 256 random bits and only its hash is stored).
-- * It reads through the invitation's own enrollment policy (the same two transaction-local pins the accept function sets) and writes
--   nothing. Executable by the enrollment pool only.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
GRANT CREATE ON SCHEMA forge TO forge_enrollment_authority;
SET LOCAL ROLE forge_enrollment_authority;
CREATE FUNCTION forge.account_invitation_preview(invitation uuid,digest text) RETURNS TABLE(account_email text,display_name text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE pending record; enabled boolean;
BEGIN
 IF invitation IS NULL OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED';
 END IF;
 PERFORM set_config('forge.enrollment_invite',invitation::text,true);
 PERFORM set_config('forge.enrollment_digest',digest,true);
 SELECT i.organization_id,i.canonical_email AS email,i.display_name AS name INTO pending FROM forge.account_invitations i
  WHERE i.id=invitation AND i.capability_hash=digest AND i.state='pending' AND i.expires_at>clock_timestamp();
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM set_config('forge.organization',pending.organization_id::text,true);
 SELECT o.active INTO enabled FROM forge.organizations o WHERE o.id=pending.organization_id;
 IF NOT FOUND OR NOT enabled THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 RETURN QUERY SELECT pending.email,pending.name;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_enrollment_authority;
REVOKE ALL ON FUNCTION forge.account_invitation_preview(uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.account_invitation_preview(uuid,text) TO forge_enrollment;
COMMIT;
