-- Company creation by the platform. Additive and forward-only: the only relaxations are two NOT NULL drops on
-- account_invitations (guarded by a CHECK that demands exactly one issuer kind) and a wider role policy on
-- membership_roles that only the accept function can open.
-- * A platform-issued invitation has NO administrator membership: it carries issuer_platform_id and the role the new
--   account receives (initial_role); only a platform issuer may ask for organization_admin, and the database enforces it.
-- * platform_company_create creates the organization, its company code (slug), the default department and the
--   first-admin invitation in ONE transaction, audits it, and answers a taken code with COMPANY_CONFLICT while creating
--   nothing. Only the digest of the capability reaches the database.
-- * accept_account_invitation keeps the member path byte-for-byte and adds the platform branch: the company must be
--   active and the issuer must still be a platform owner, and the role comes from the invitation row, never from the
--   caller (the role context is overwritten by the function before any insert).
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

ALTER TABLE forge.account_invitations
 ALTER COLUMN administrator_membership_id DROP NOT NULL,
 ALTER COLUMN administrator_identity_id DROP NOT NULL,
 ADD COLUMN issuer_platform_id uuid REFERENCES forge.owned_accounts(id),
 ADD COLUMN initial_role text NOT NULL DEFAULT 'member' CHECK(initial_role IN ('member','organization_admin')),
 ADD CONSTRAINT invitation_one_issuer CHECK(
  (administrator_membership_id IS NOT NULL AND administrator_identity_id IS NOT NULL AND issuer_platform_id IS NULL)
  OR (administrator_membership_id IS NULL AND administrator_identity_id IS NULL AND issuer_platform_id IS NOT NULL)),
 ADD CONSTRAINT invitation_admin_role_platform_only CHECK(initial_role='member' OR issuer_platform_id IS NOT NULL);

-- The authority writes the four rows of a new company, each only for the organization named by the context a function set.
GRANT INSERT ON forge.organizations,forge.configuration_revisions,forge.departments,forge.account_invitations
 TO forge_platform_authority;
CREATE POLICY platform_create ON forge.organizations FOR INSERT TO forge_platform_authority
 WITH CHECK(id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_create ON forge.configuration_revisions FOR INSERT TO forge_platform_authority
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_create ON forge.departments FOR INSERT TO forge_platform_authority
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY platform_issue ON forge.account_invitations FOR INSERT TO forge_platform_authority
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization') AND issuer_platform_id IS NOT NULL
  AND initial_role='organization_admin' AND state='pending');

-- membership_roles: the role must equal the role context (default member). Only accept_account_invitation sets it, from
-- the invitation row, immediately before its own insert.
DROP POLICY enrollment_authority ON forge.membership_roles;
DROP POLICY enrollment_limit ON forge.membership_roles;
CREATE POLICY enrollment_authority ON forge.membership_roles TO forge_enrollment_authority
 USING(organization_id=forge.context_organization())
 WITH CHECK(organization_id=forge.context_organization() AND role IN ('member','organization_admin')
    AND role=coalesce(nullif(current_setting('forge.enrollment_role',true),''),'member')
    AND membership_id=forge.enrollment_uuid('forge.enrollment_member'));
CREATE POLICY enrollment_limit ON forge.membership_roles AS RESTRICTIVE TO forge_enrollment_authority
 USING(organization_id=forge.context_organization())
 WITH CHECK(organization_id=forge.context_organization() AND role IN ('member','organization_admin')
    AND role=coalesce(nullif(current_setting('forge.enrollment_role',true),''),'member')
    AND membership_id=forge.enrollment_uuid('forge.enrollment_member'));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- Internal, for the accept function: is this account still a platform owner?
CREATE FUNCTION forge.platform_owner_exists(account uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM forge.platform_roles r WHERE r.account_id=account AND r.role='platform_owner')
$$;

CREATE FUNCTION forge.platform_company_create(digest text,org uuid,dept uuid,invitation uuid,member uuid,
 company_slug text,company_name text,dept_name text,admin_email text,admin_name text,hashed text,lifetime integer)
RETURNS timestamptz
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; expires timestamptz;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF org IS NULL OR dept IS NULL OR invitation IS NULL OR member IS NULL
  OR company_slug IS NULL OR company_slug !~ '^[a-z0-9][a-z0-9-]{0,62}$'
  OR company_name IS NULL OR company_name<>btrim(company_name) OR length(company_name) NOT BETWEEN 1 AND 120
  OR dept_name IS NULL OR dept_name<>btrim(dept_name) OR length(dept_name) NOT BETWEEN 1 AND 120
  OR admin_email IS NULL OR admin_email<>lower(btrim(admin_email)) OR length(admin_email) NOT BETWEEN 3 AND 254
  OR admin_email !~ '^[!-~]+@[!-~]+$'
  OR admin_name IS NULL OR admin_name<>btrim(admin_name) OR length(admin_name) NOT BETWEEN 1 AND 120
  OR hashed IS NULL OR hashed !~ '^[0-9a-f]{64}$' OR lifetime IS NULL OR lifetime<60 OR lifetime>604800 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 PERFORM set_config('forge.organization',org::text,true);
 expires:=clock_timestamp()+make_interval(secs=>lifetime);
 BEGIN
  INSERT INTO forge.organizations(id,slug,display_name,active,selected_config_revision)
   VALUES(org,company_slug,company_name,true,1);
  INSERT INTO forge.configuration_revisions(organization_id,revision) VALUES(org,1);
  INSERT INTO forge.departments(organization_id,id,name) VALUES(org,dept,dept_name);
  INSERT INTO forge.account_invitations(id,organization_id,issuer_platform_id,initial_role,membership_id,department_id,
   canonical_email,display_name,capability_hash,expires_at)
   VALUES(invitation,org,actor,'organization_admin',member,dept,admin_email,admin_name,hashed,expires);
 EXCEPTION WHEN unique_violation THEN
  -- The subtransaction rolls back every row above: a taken company code creates nothing.
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='COMPANY_CONFLICT';
 END;
 PERFORM forge.platform_audit_write(actor,'company.created',org);
 RETURN expires;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_owner_exists(uuid),
 forge.platform_company_create(text,uuid,uuid,uuid,uuid,text,text,text,text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_company_create(text,uuid,uuid,uuid,uuid,text,text,text,text,text,text,integer)
 TO forge_platform_service;
GRANT EXECUTE ON FUNCTION forge.platform_owner_exists(uuid) TO forge_enrollment_authority;

GRANT CREATE ON SCHEMA forge TO forge_enrollment_authority;
SET LOCAL ROLE forge_enrollment_authority;
CREATE OR REPLACE FUNCTION forge.accept_account_invitation(invitation uuid, digest text,
    account uuid, encoded text) RETURNS TABLE(account_id uuid,membership_id uuid,
        organization_id uuid,department_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE pending record; principal record; ident uuid; enabled boolean;
BEGIN
 IF invitation IS NULL OR account IS NULL OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$'
    OR encoded IS NULL OR encoded !~ '^forge\$scrypt\$v1\$131072\$8\$1\$[A-Za-z0-9_-]{22}\$[A-Za-z0-9_-]{43}$'
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM set_config('forge.enrollment_invite',invitation::text,true);
 PERFORM set_config('forge.enrollment_digest',digest,true);
 SELECT * INTO pending FROM forge.account_invitations WHERE id=invitation AND capability_hash=digest;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 IF pending.issuer_platform_id IS NULL THEN
  -- Member path: an administrator issued it and must still be one (unchanged from 0013).
  PERFORM set_config('forge.enrollment_actor',pending.administrator_identity_id::text,true);
  SELECT * INTO principal FROM forge.identities WHERE id=pending.administrator_identity_id;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
  ident:=forge.enrollment_lock_admin(pending.organization_id,pending.administrator_membership_id,
     principal.provider,principal.issuer,principal.subject);
  IF ident IS NULL OR ident<>pending.administrator_identity_id
  THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 ELSE
  -- Platform path: the company must be active and the issuer must still be a platform owner.
  PERFORM set_config('forge.organization',pending.organization_id::text,true);
  SELECT o.active INTO enabled FROM forge.organizations o WHERE o.id=pending.organization_id FOR UPDATE;
  IF NOT FOUND OR NOT enabled OR NOT forge.platform_owner_exists(pending.issuer_platform_id)
  THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 END IF;
 PERFORM 1 FROM forge.departments d WHERE d.organization_id=pending.organization_id
    AND d.id=pending.department_id AND d.active FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 -- Re-read after all authority locks; expiry checked at consume time, not peek time.
 SELECT * INTO pending FROM forge.account_invitations WHERE id=invitation
    AND capability_hash=digest AND state='pending' AND expires_at>clock_timestamp() FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 IF pending.expires_at<=clock_timestamp()
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM set_config('forge.enrollment_email',pending.canonical_email,true);
 IF EXISTS(SELECT 1 FROM forge.owned_accounts a WHERE a.canonical_email=pending.canonical_email)
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='EXISTING_ACCOUNT_AUTH_REQUIRED'; END IF;
 PERFORM set_config('forge.enrollment_identity',account::text,true);
 PERFORM set_config('forge.enrollment_member',pending.membership_id::text,true);
 -- The role is the invitation's, never the caller's: whatever the caller put here is overwritten.
 PERFORM set_config('forge.enrollment_role',pending.initial_role,true);
 INSERT INTO forge.identities(id,provider,issuer,subject)
    VALUES(account,'forge','urn:prometheon:forge:accounts:v1',account::text);
 INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash)
    VALUES(account,pending.canonical_email,pending.display_name,encoded);
 INSERT INTO forge.memberships(organization_id,id,identity_id,status)
    VALUES(pending.organization_id,pending.membership_id,account,'active');
 INSERT INTO forge.membership_roles(organization_id,membership_id,role)
    VALUES(pending.organization_id,pending.membership_id,pending.initial_role);
 INSERT INTO forge.membership_departments(organization_id,membership_id,department_id)
    VALUES(pending.organization_id,pending.membership_id,pending.department_id);
 UPDATE forge.account_invitations SET state='accepted',consumed_at=clock_timestamp(),account_id=account
    WHERE id=invitation;
 INSERT INTO forge.account_enrollment_audit(event_id,organization_id,actor_id,invitation_id,event_type)
    VALUES(gen_random_uuid(),pending.organization_id,
        coalesce(pending.administrator_membership_id,pending.membership_id),invitation,'invitation.accepted');
 RETURN QUERY SELECT account,pending.membership_id,pending.organization_id,pending.department_id;
EXCEPTION WHEN unique_violation THEN
 -- The entire function subtransaction rolls back: existing credential is never updated.
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='EXISTING_ACCOUNT_AUTH_REQUIRED';
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_enrollment_authority;
COMMIT;
