-- Additive owned-account enrollment; trusted installer, no seeded account or LOGIN.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_enrollment NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_enrollment_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_enrollment',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_enrollment,forge_enrollment_authority;

CREATE TABLE forge.departments (
    organization_id uuid NOT NULL REFERENCES forge.organizations(id),
    id uuid NOT NULL,
    name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
    active boolean NOT NULL DEFAULT true,
    revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
    PRIMARY KEY(organization_id,id)
);
CREATE TABLE forge.owned_accounts (
    id uuid PRIMARY KEY REFERENCES forge.identities(id),
    canonical_email text NOT NULL UNIQUE CHECK(canonical_email=lower(btrim(canonical_email))
        AND length(canonical_email) BETWEEN 3 AND 254 AND canonical_email ~ '^[!-~]+@[!-~]+$'),
    display_name text NOT NULL CHECK(length(btrim(display_name)) BETWEEN 1 AND 120),
    password_hash text NOT NULL CHECK(password_hash ~
        '^forge\$scrypt\$v1\$131072\$8\$1\$[A-Za-z0-9_-]{22}\$[A-Za-z0-9_-]{43}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE forge.account_invitations (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES forge.organizations(id),
    administrator_membership_id uuid NOT NULL,
    administrator_identity_id uuid NOT NULL REFERENCES forge.identities(id),
    membership_id uuid NOT NULL,
    department_id uuid NOT NULL,
    canonical_email text NOT NULL CHECK(length(canonical_email) BETWEEN 3 AND 254
        AND canonical_email=lower(btrim(canonical_email))),
    display_name text NOT NULL CHECK(length(btrim(display_name)) BETWEEN 1 AND 120),
    capability_hash text NOT NULL UNIQUE CHECK(capability_hash ~ '^[0-9a-f]{64}$'),
    state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','revoked')),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    account_id uuid REFERENCES forge.owned_accounts(id),
    FOREIGN KEY(organization_id,administrator_membership_id)
        REFERENCES forge.memberships(organization_id,id),
    FOREIGN KEY(organization_id,department_id) REFERENCES forge.departments(organization_id,id),
    UNIQUE(organization_id,membership_id),
    CHECK((state='accepted' AND consumed_at IS NOT NULL AND account_id IS NOT NULL)
          OR (state<>'accepted' AND consumed_at IS NULL AND account_id IS NULL))
);
CREATE TABLE forge.membership_departments (
    organization_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    department_id uuid NOT NULL,
    PRIMARY KEY(organization_id,membership_id,department_id),
    FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id),
    FOREIGN KEY(organization_id,department_id) REFERENCES forge.departments(organization_id,id)
);
-- Deliberate fixed audit columns: no email, name, password, hash or raw capability.
CREATE TABLE forge.account_enrollment_audit (
    event_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    invitation_id uuid NOT NULL REFERENCES forge.account_invitations(id),
    event_type text NOT NULL CHECK(event_type IN ('invitation.issued','invitation.revoked','invitation.accepted')),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(organization_id,actor_id) REFERENCES forge.memberships(organization_id,id)
);

CREATE FUNCTION forge.enrollment_uuid(key text) RETURNS uuid
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT CASE WHEN current_setting(key,true) ~
 '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
 THEN current_setting(key,true)::uuid ELSE NULL END
$$;
REVOKE ALL ON FUNCTION forge.enrollment_uuid(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),forge.context_organization(),
    forge.context_ready(),forge.has_membership(uuid) TO forge_enrollment_authority;

GRANT SELECT ON forge.organizations,forge.memberships,forge.identities,
    forge.membership_roles TO forge_enrollment_authority;
GRANT UPDATE(id) ON forge.organizations,forge.identities TO forge_enrollment_authority;
GRANT UPDATE(organization_id) ON forge.memberships,forge.membership_roles TO forge_enrollment_authority;
GRANT INSERT ON forge.identities,forge.memberships,forge.membership_roles TO forge_enrollment_authority;

CREATE POLICY enrollment_authority ON forge.organizations TO forge_enrollment_authority
 USING(id=forge.context_organization()) WITH CHECK(false);
CREATE POLICY enrollment_limit ON forge.organizations AS RESTRICTIVE TO forge_enrollment_authority
 USING(id=forge.context_organization()) WITH CHECK(false);
CREATE POLICY enrollment_authority ON forge.memberships TO forge_enrollment_authority
 USING(organization_id=forge.context_organization())
 WITH CHECK(organization_id=forge.context_organization() AND status='active'
    AND id=forge.enrollment_uuid('forge.enrollment_member')
    AND identity_id=forge.enrollment_uuid('forge.enrollment_identity'));
CREATE POLICY enrollment_limit ON forge.memberships AS RESTRICTIVE TO forge_enrollment_authority
 USING(organization_id=forge.context_organization())
 WITH CHECK(organization_id=forge.context_organization() AND status='active'
    AND id=forge.enrollment_uuid('forge.enrollment_member')
    AND identity_id=forge.enrollment_uuid('forge.enrollment_identity'));
CREATE POLICY enrollment_authority ON forge.identities TO forge_enrollment_authority
 USING(id IN (forge.enrollment_uuid('forge.enrollment_actor'),forge.enrollment_uuid('forge.enrollment_identity')))
 WITH CHECK(id=forge.enrollment_uuid('forge.enrollment_identity') AND provider='forge'
    AND issuer='urn:prometheon:forge:accounts:v1' AND subject=id::text
    AND entra_tenant_id IS NULL AND entra_object_id IS NULL);
CREATE POLICY enrollment_limit ON forge.identities AS RESTRICTIVE TO forge_enrollment_authority
 USING(id IN (forge.enrollment_uuid('forge.enrollment_actor'),forge.enrollment_uuid('forge.enrollment_identity')))
 WITH CHECK(id=forge.enrollment_uuid('forge.enrollment_identity') AND provider='forge'
    AND issuer='urn:prometheon:forge:accounts:v1' AND subject=id::text
    AND entra_tenant_id IS NULL AND entra_object_id IS NULL);
CREATE POLICY enrollment_authority ON forge.membership_roles TO forge_enrollment_authority
 USING(organization_id=forge.context_organization())
 WITH CHECK(organization_id=forge.context_organization() AND role='member'
    AND membership_id=forge.enrollment_uuid('forge.enrollment_member'));
CREATE POLICY enrollment_limit ON forge.membership_roles AS RESTRICTIVE TO forge_enrollment_authority
 USING(organization_id=forge.context_organization())
 WITH CHECK(organization_id=forge.context_organization() AND role='member'
    AND membership_id=forge.enrollment_uuid('forge.enrollment_member'));

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['departments','owned_accounts','account_invitations',
                          'membership_departments','account_enrollment_audit'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment',t);
 END LOOP;
END $$;
GRANT SELECT ON forge.departments TO forge_enrollment_authority;
GRANT UPDATE(id) ON forge.departments TO forge_enrollment_authority;
GRANT SELECT,INSERT ON forge.owned_accounts TO forge_enrollment_authority;
GRANT SELECT,INSERT,UPDATE ON forge.account_invitations TO forge_enrollment_authority;
GRANT INSERT ON forge.membership_departments,forge.account_enrollment_audit TO forge_enrollment_authority;
CREATE POLICY enrollment_scope ON forge.departments TO forge_enrollment_authority
 USING(organization_id=forge.context_organization()) WITH CHECK(false);
CREATE POLICY enrollment_scope ON forge.owned_accounts TO forge_enrollment_authority
 USING(canonical_email=current_setting('forge.enrollment_email',true))
 WITH CHECK(canonical_email=current_setting('forge.enrollment_email',true)
    AND id=forge.enrollment_uuid('forge.enrollment_identity'));
CREATE POLICY enrollment_scope ON forge.account_invitations TO forge_enrollment_authority
 USING(organization_id=forge.context_organization() OR
    (id=forge.enrollment_uuid('forge.enrollment_invite')
     AND capability_hash=current_setting('forge.enrollment_digest',true)))
 WITH CHECK(organization_id=forge.context_organization());
CREATE POLICY enrollment_scope ON forge.membership_departments TO forge_enrollment_authority
 WITH CHECK(organization_id=forge.context_organization()
    AND membership_id=forge.enrollment_uuid('forge.enrollment_member'));
CREATE POLICY enrollment_scope ON forge.account_enrollment_audit TO forge_enrollment_authority
 WITH CHECK(organization_id=forge.context_organization());

-- Internal fresh authorization/locks. No execute permission to caller/PUBLIC.
CREATE FUNCTION forge.enrollment_lock_admin(org uuid, member uuid,
    provider text, issuer text, subject text) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE enabled boolean; ident uuid; state text; principal record;
BEGIN
 IF org IS NULL OR member IS NULL THEN RETURN NULL; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 SELECT active INTO enabled FROM forge.organizations WHERE id=org FOR UPDATE;
 IF NOT FOUND OR NOT enabled THEN RETURN NULL; END IF;
 SELECT identity_id,status INTO ident,state FROM forge.memberships
    WHERE organization_id=org AND id=member FOR UPDATE;
 IF NOT FOUND OR state<>'active' THEN RETURN NULL; END IF;
 PERFORM set_config('forge.enrollment_actor',ident::text,true);
 SELECT * INTO principal FROM forge.identities WHERE id=ident FOR UPDATE;
 IF NOT FOUND OR principal.provider IS DISTINCT FROM provider
    OR principal.issuer IS DISTINCT FROM issuer OR principal.subject IS DISTINCT FROM subject
    OR (principal.provider='entra' AND (principal.entra_tenant_id IS NULL
        OR principal.entra_object_id IS NULL OR principal.subject<>principal.entra_object_id::text
        OR principal.issuer<>'https://login.microsoftonline.com/'||principal.entra_tenant_id::text||'/v2.0'))
 THEN RETURN NULL; END IF;
 PERFORM 1 FROM forge.membership_roles WHERE organization_id=org
    AND membership_id=member AND role='organization_admin' FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN ident;
END $$;

CREATE FUNCTION forge.issue_account_invitation(org uuid, actor uuid, provider text,
    issuer text, subject text, dept uuid, invitation uuid, member uuid,
    email text, name text, digest text, lifetime integer) RETURNS timestamptz
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE ident uuid; expires timestamptz;
BEGIN
 IF digest IS NULL OR digest !~ '^[0-9a-f]{64}$' OR lifetime IS NULL
    OR lifetime<60 OR lifetime>604800 OR email IS NULL OR email<>lower(btrim(email))
    OR length(email)>254 OR name IS NULL OR length(btrim(name)) NOT BETWEEN 1 AND 120
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 ident:=forge.enrollment_lock_admin(org,actor,provider,issuer,subject);
 IF ident IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM 1 FROM forge.departments WHERE organization_id=org AND id=dept AND active FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 expires:=clock_timestamp()+make_interval(secs=>lifetime);
 INSERT INTO forge.account_invitations(id,organization_id,administrator_membership_id,
    administrator_identity_id,membership_id,department_id,canonical_email,display_name,
    capability_hash,expires_at) VALUES(invitation,org,actor,ident,member,dept,email,name,digest,expires);
 INSERT INTO forge.account_enrollment_audit(event_id,organization_id,actor_id,invitation_id,event_type)
    VALUES(gen_random_uuid(),org,actor,invitation,'invitation.issued');
 RETURN expires;
END $$;

CREATE FUNCTION forge.revoke_account_invitation(org uuid, actor uuid, provider text,
    issuer text, subject text, invitation uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF forge.enrollment_lock_admin(org,actor,provider,issuer,subject) IS NULL
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM 1 FROM forge.account_invitations WHERE id=invitation AND organization_id=org
    AND state='pending' FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 UPDATE forge.account_invitations SET state='revoked' WHERE id=invitation;
 INSERT INTO forge.account_enrollment_audit(event_id,organization_id,actor_id,invitation_id,event_type)
    VALUES(gen_random_uuid(),org,actor,invitation,'invitation.revoked');
 RETURN true;
END $$;

CREATE FUNCTION forge.accept_account_invitation(invitation uuid, digest text,
    account uuid, encoded text) RETURNS TABLE(account_id uuid,membership_id uuid,
        organization_id uuid,department_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE pending record; principal record; ident uuid;
BEGIN
 IF invitation IS NULL OR account IS NULL OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$'
    OR encoded IS NULL OR encoded !~ '^forge\$scrypt\$v1\$131072\$8\$1\$[A-Za-z0-9_-]{22}\$[A-Za-z0-9_-]{43}$'
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM set_config('forge.enrollment_invite',invitation::text,true);
 PERFORM set_config('forge.enrollment_digest',digest,true);
 SELECT * INTO pending FROM forge.account_invitations WHERE id=invitation AND capability_hash=digest;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 PERFORM set_config('forge.enrollment_actor',pending.administrator_identity_id::text,true);
 SELECT * INTO principal FROM forge.identities WHERE id=pending.administrator_identity_id;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
 ident:=forge.enrollment_lock_admin(pending.organization_id,pending.administrator_membership_id,
    principal.provider,principal.issuer,principal.subject);
 IF ident IS NULL OR ident<>pending.administrator_identity_id
 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='INVITATION_DENIED'; END IF;
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
 INSERT INTO forge.identities(id,provider,issuer,subject)
    VALUES(account,'forge','urn:prometheon:forge:accounts:v1',account::text);
 INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash)
    VALUES(account,pending.canonical_email,pending.display_name,encoded);
 INSERT INTO forge.memberships(organization_id,id,identity_id,status)
    VALUES(pending.organization_id,pending.membership_id,account,'active');
 INSERT INTO forge.membership_roles(organization_id,membership_id,role)
    VALUES(pending.organization_id,pending.membership_id,'member');
 INSERT INTO forge.membership_departments(organization_id,membership_id,department_id)
    VALUES(pending.organization_id,pending.membership_id,pending.department_id);
 UPDATE forge.account_invitations SET state='accepted',consumed_at=clock_timestamp(),account_id=account
    WHERE id=invitation;
 INSERT INTO forge.account_enrollment_audit(event_id,organization_id,actor_id,invitation_id,event_type)
    VALUES(gen_random_uuid(),pending.organization_id,pending.administrator_membership_id,
        invitation,'invitation.accepted');
 RETURN QUERY SELECT account,pending.membership_id,pending.organization_id,pending.department_id;
EXCEPTION WHEN unique_violation THEN
 -- The entire function subtransaction rolls back: existing credential is never updated.
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='EXISTING_ACCOUNT_AUTH_REQUIRED';
END $$;
REVOKE ALL ON FUNCTION forge.enrollment_lock_admin(uuid,uuid,text,text,text),
    forge.issue_account_invitation(uuid,uuid,text,text,text,uuid,uuid,uuid,text,text,text,integer),
    forge.revoke_account_invitation(uuid,uuid,text,text,text,uuid),
    forge.accept_account_invitation(uuid,text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
    forge.issue_account_invitation(uuid,uuid,text,text,text,uuid,uuid,uuid,text,text,text,integer),
    forge.revoke_account_invitation(uuid,uuid,text,text,text,uuid),
    forge.accept_account_invitation(uuid,text,uuid,text) TO forge_enrollment;
RESET ROLE;
-- Ownership is narrowly transferred by trusted installer; no caller SET ROLE edges.
GRANT CREATE ON SCHEMA forge TO forge_enrollment_authority;
ALTER FUNCTION forge.enrollment_lock_admin(uuid,uuid,text,text,text) OWNER TO forge_enrollment_authority;
ALTER FUNCTION forge.issue_account_invitation(uuid,uuid,text,text,text,uuid,uuid,uuid,text,text,text,integer)
    OWNER TO forge_enrollment_authority;
ALTER FUNCTION forge.revoke_account_invitation(uuid,uuid,text,text,text,uuid) OWNER TO forge_enrollment_authority;
ALTER FUNCTION forge.accept_account_invitation(uuid,text,uuid,text) OWNER TO forge_enrollment_authority;
REVOKE CREATE ON SCHEMA forge FROM forge_enrollment_authority;
COMMIT;
