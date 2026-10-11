-- Opt-in owned accounts: hashed sessions/reset capabilities and encrypted delivery.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_account_service NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_account_service',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_account_service;
ALTER TABLE forge.owned_accounts
 ADD COLUMN active boolean NOT NULL DEFAULT true,
 ADD COLUMN credential_revision bigint NOT NULL DEFAULT 1 CHECK(credential_revision>0),
 ADD COLUMN login_attempts integer NOT NULL DEFAULT 0 CHECK(login_attempts BETWEEN 0 AND 5),
 ADD COLUMN login_window timestamptz,
 ADD COLUMN reset_requested_at timestamptz;
GRANT UPDATE ON forge.owned_accounts TO forge_enrollment_authority;
CREATE POLICY account_identity_scope ON forge.owned_accounts TO forge_enrollment_authority
 USING(id=forge.enrollment_uuid('forge.enrollment_identity'))
 WITH CHECK(id=forge.enrollment_uuid('forge.enrollment_identity'));
-- Hash-only generic lookup throttling also covers unknown addresses. No public
-- registration/identity is created. Global capacity is finite and expired rows
-- are removed under a fixed transaction lock before admitting another key.
CREATE TABLE forge.account_login_buckets (
 lookup_hash text PRIMARY KEY CHECK(lookup_hash ~ '^[0-9a-f]{64}$'),
 attempts integer NOT NULL CHECK(attempts BETWEEN 1 AND 5),
 expires_at timestamptz NOT NULL
);
ALTER TABLE forge.account_login_buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.account_login_buckets FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.account_login_buckets FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service;
GRANT SELECT,INSERT,UPDATE,DELETE ON forge.account_login_buckets TO forge_enrollment_authority;
-- Deliberately global finite throttle state, not tenant/business data; only the
-- nonlogin function owner can inspect it. Applications have no direct table ACL.
CREATE POLICY throttle_owner ON forge.account_login_buckets TO forge_enrollment_authority
 USING(true) WITH CHECK(true);
CREATE TABLE forge.account_sessions (
 capability_hash text PRIMARY KEY CHECK(capability_hash ~ '^[0-9a-f]{64}$'),
 account_id uuid NOT NULL REFERENCES forge.owned_accounts(id),
 credential_revision bigint NOT NULL CHECK(credential_revision>0),
 expires_at timestamptz NOT NULL,
 revoked boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX account_sessions_account ON forge.account_sessions(account_id);
CREATE TABLE forge.account_password_resets (
 capability_hash text PRIMARY KEY CHECK(capability_hash ~ '^[0-9a-f]{64}$'),
 account_id uuid NOT NULL REFERENCES forge.owned_accounts(id),
 credential_revision bigint NOT NULL CHECK(credential_revision>0),
 expires_at timestamptz NOT NULL,
 consumed boolean NOT NULL DEFAULT false
);
CREATE TABLE forge.account_message_delivery (
 id uuid PRIMARY KEY,
 organization_id uuid REFERENCES forge.organizations(id),
 invitation_id uuid REFERENCES forge.account_invitations(id),
 reset_hash text REFERENCES forge.account_password_resets(capability_hash),
 CHECK(num_nonnulls(invitation_id,reset_hash)=1),
 encrypted_payload text NOT NULL CHECK(length(encrypted_payload) BETWEEN 100 AND 16384),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','delivered','failed')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 lease_token uuid,
 lease_until timestamptz,
 CHECK((lease_token IS NULL)=(lease_until IS NULL)),
 expires_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['account_sessions','account_password_resets','account_message_delivery'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON forge.%I TO forge_enrollment_authority',t);
 END LOOP;
END $$;
CREATE POLICY account_scope ON forge.account_sessions TO forge_enrollment_authority
 USING(account_id=forge.enrollment_uuid('forge.enrollment_identity')
       OR capability_hash=current_setting('forge.account_digest',true))
 WITH CHECK(account_id=forge.enrollment_uuid('forge.enrollment_identity'));
CREATE POLICY account_scope ON forge.account_password_resets TO forge_enrollment_authority
 USING(account_id=forge.enrollment_uuid('forge.enrollment_identity')
       OR capability_hash=current_setting('forge.account_digest',true))
 WITH CHECK(account_id=forge.enrollment_uuid('forge.enrollment_identity'));
CREATE POLICY message_scope ON forge.account_message_delivery TO forge_enrollment_authority
 USING(id=forge.enrollment_uuid('forge.account_message'))
 WITH CHECK(id=forge.enrollment_uuid('forge.account_message'));

CREATE FUNCTION forge.account_lock(account uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF account IS NULL THEN RETURN false; END IF;
 PERFORM set_config('forge.enrollment_identity',account::text,true);
 PERFORM 1 FROM forge.owned_accounts a WHERE a.id=account FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM 1 FROM forge.identities i WHERE i.id=account AND i.provider='forge'
  AND i.issuer='urn:prometheon:forge:accounts:v1' AND i.subject=account::text
  AND i.entra_tenant_id IS NULL AND i.entra_object_id IS NULL;
 RETURN FOUND;
END $$;

-- Reserve a password attempt durably BEFORE expensive verification. Failure never
-- needs a rollback-producing exception, and parallel guesses consume one budget.
CREATE FUNCTION forge.account_begin_login(email text)
RETURNS TABLE(account_id uuid,encoded text,revision bigint,retry_seconds integer)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record; retry integer; key text; bucket record;
BEGIN
 IF email IS NULL OR length(email)>254 OR email<>lower(btrim(email)) THEN RETURN; END IF;
 key:=encode(sha256(convert_to(email,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(13680001);
 DELETE FROM forge.account_login_buckets b WHERE b.expires_at<=clock_timestamp();
 SELECT * INTO bucket FROM forge.account_login_buckets b WHERE b.lookup_hash=key FOR UPDATE;
 IF FOUND THEN
  IF bucket.attempts>=5 THEN
   retry:=greatest(1,ceil(extract(epoch FROM bucket.expires_at-clock_timestamp()))::integer);
   RETURN QUERY SELECT NULL::uuid,NULL::text,1::bigint,retry;
   RETURN;
  END IF;
  UPDATE forge.account_login_buckets SET attempts=attempts+1 WHERE lookup_hash=key;
 ELSE
  IF (SELECT count(*) FROM forge.account_login_buckets)>=10000 THEN
   RETURN QUERY SELECT NULL::uuid,NULL::text,1::bigint,900;
   RETURN;
  END IF;
  INSERT INTO forge.account_login_buckets VALUES(key,1,clock_timestamp()+interval '15 minutes');
 END IF;
 PERFORM set_config('forge.enrollment_email',email,true);
 SELECT * INTO a FROM forge.owned_accounts x WHERE x.canonical_email=email FOR UPDATE;
 IF NOT FOUND THEN RETURN; END IF;
 IF NOT forge.account_lock(a.id) THEN RETURN; END IF;
 IF NOT a.active THEN RETURN; END IF;
 IF a.login_window IS NULL OR a.login_window<=clock_timestamp()-interval '15 minutes' THEN
  UPDATE forge.owned_accounts SET login_attempts=0,login_window=clock_timestamp() WHERE id=a.id;
  a.login_attempts:=0; a.login_window:=clock_timestamp();
 END IF;
 IF a.login_attempts>=5 THEN
  retry:=greatest(1,ceil(extract(epoch FROM a.login_window+interval '15 minutes'-clock_timestamp()))::integer);
  RETURN QUERY SELECT a.id,NULL::text,a.credential_revision,retry;
  RETURN;
 END IF;
 UPDATE forge.owned_accounts SET login_attempts=login_attempts+1 WHERE id=a.id;
 RETURN QUERY SELECT a.id,a.password_hash,a.credential_revision,0;
END $$;

CREATE FUNCTION forge.account_finish_login(account uuid,expected_revision bigint,
 expected_hash text,digest text) RETURNS timestamptz
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE expires timestamptz; email text;
BEGIN
 -- Match begin_login's bucket-before-account lock order; never invert it.
 PERFORM pg_advisory_xact_lock(13680001);
 IF digest IS NULL OR digest !~ '^[0-9a-f]{64}$' OR NOT forge.account_lock(account) THEN RETURN NULL; END IF;
 PERFORM 1 FROM forge.owned_accounts a WHERE a.id=account AND a.active
  AND a.credential_revision=expected_revision AND a.password_hash=expected_hash;
 IF NOT FOUND THEN RETURN NULL; END IF;
 -- Bounded live-session count; prune expired/revoked rows under the account lock.
 DELETE FROM forge.account_sessions s WHERE s.account_id=account AND (s.revoked OR s.expires_at<=clock_timestamp());
 IF (SELECT count(*) FROM forge.account_sessions s WHERE s.account_id=account)>=8 THEN RETURN NULL; END IF;
 expires:=clock_timestamp()+interval '8 hours';
 INSERT INTO forge.account_sessions(capability_hash,account_id,credential_revision,expires_at)
 VALUES(digest,account,expected_revision,expires);
 UPDATE forge.owned_accounts SET login_attempts=0,login_window=NULL WHERE id=account;
 SELECT a.canonical_email INTO email FROM forge.owned_accounts a WHERE a.id=account;
 DELETE FROM forge.account_login_buckets WHERE lookup_hash=encode(sha256(convert_to(email,'UTF8')),'hex');
 RETURN expires;
END $$;

CREATE FUNCTION forge.account_validate_session(digest text) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 IF digest IS NULL OR digest !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
 PERFORM set_config('forge.account_digest',digest,true);
 SELECT s.account_id INTO account FROM forge.account_sessions s WHERE s.capability_hash=digest;
 IF NOT forge.account_lock(account) THEN RETURN NULL; END IF;
 PERFORM 1 FROM forge.account_sessions s JOIN forge.owned_accounts a ON a.id=s.account_id
  WHERE s.capability_hash=digest AND NOT s.revoked AND s.expires_at>clock_timestamp()
   AND a.active AND a.credential_revision=s.credential_revision;
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN account;
END $$;

CREATE FUNCTION forge.account_logout(digest text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL THEN RETURN false; END IF;
 UPDATE forge.account_sessions SET revoked=true WHERE capability_hash=digest;
 RETURN true;
END $$;

CREATE FUNCTION forge.account_disable(digest text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL THEN RETURN false; END IF;
 UPDATE forge.owned_accounts SET active=false,credential_revision=credential_revision+1 WHERE id=account;
 UPDATE forge.account_sessions SET revoked=true WHERE account_id=account;
 UPDATE forge.account_password_resets SET consumed=true WHERE account_id=account;
 RETURN true;
END $$;

CREATE FUNCTION forge.account_request_reset(email text,digest text)
RETURNS TABLE(account_id uuid,recipient text,name text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record;
BEGIN
 IF email IS NULL OR length(email)>254 OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$' THEN RETURN; END IF;
 PERFORM set_config('forge.enrollment_email',email,true);
 SELECT * INTO a FROM forge.owned_accounts x WHERE x.canonical_email=email FOR UPDATE;
 IF NOT FOUND OR NOT a.active OR NOT forge.account_lock(a.id) THEN RETURN; END IF;
 IF a.reset_requested_at IS NOT NULL AND a.reset_requested_at>clock_timestamp()-interval '1 minute' THEN RETURN; END IF;
 UPDATE forge.account_password_resets r SET consumed=true WHERE r.account_id=a.id;
 INSERT INTO forge.account_password_resets(capability_hash,account_id,credential_revision,expires_at)
 VALUES(digest,a.id,a.credential_revision,clock_timestamp()+interval '30 minutes');
 UPDATE forge.owned_accounts SET reset_requested_at=clock_timestamp() WHERE id=a.id;
 RETURN QUERY SELECT a.id,a.canonical_email,a.display_name;
END $$;

CREATE FUNCTION forge.account_consume_reset(digest text,encoded text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 IF digest IS NULL OR digest !~ '^[0-9a-f]{64}$' OR encoded IS NULL
  OR encoded !~ '^forge\$scrypt\$v1\$131072\$8\$1\$[A-Za-z0-9_-]{22}\$[A-Za-z0-9_-]{43}$'
 THEN RETURN false; END IF;
 PERFORM set_config('forge.account_digest',digest,true);
 SELECT r.account_id INTO account FROM forge.account_password_resets r WHERE r.capability_hash=digest;
 IF NOT forge.account_lock(account) THEN RETURN false; END IF;
 PERFORM 1 FROM forge.account_password_resets r JOIN forge.owned_accounts a ON a.id=r.account_id
  WHERE r.capability_hash=digest AND NOT r.consumed AND r.expires_at>clock_timestamp()
   AND a.active AND a.credential_revision=r.credential_revision FOR UPDATE OF r;
 IF NOT FOUND THEN RETURN false; END IF;
 UPDATE forge.owned_accounts SET password_hash=encoded,credential_revision=credential_revision+1,
  login_attempts=0,login_window=NULL WHERE id=account;
 UPDATE forge.account_password_resets SET consumed=true WHERE account_id=account;
 UPDATE forge.account_sessions SET revoked=true WHERE account_id=account;
 RETURN true;
END $$;

CREATE FUNCTION forge.account_queue_message(message uuid,invitation uuid,digest text,payload text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE expires timestamptz; org uuid;
BEGIN
 IF message IS NULL OR invitation IS NULL OR payload IS NULL OR length(payload) NOT BETWEEN 100 AND 16384
  OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
 PERFORM set_config('forge.enrollment_invite',invitation::text,true);
 PERFORM set_config('forge.enrollment_digest',digest,true);
 SELECT i.expires_at,i.organization_id INTO expires,org FROM forge.account_invitations i WHERE i.id=invitation
  AND i.capability_hash=digest AND i.state='pending' AND i.expires_at>clock_timestamp() FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM set_config('forge.account_message',message::text,true);
 INSERT INTO forge.account_message_delivery(id,organization_id,invitation_id,encrypted_payload,expires_at)
 VALUES(message,org,invitation,payload,expires);
 RETURN true;
END $$;

CREATE FUNCTION forge.account_queue_reset_message(message uuid,digest text,payload text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE expires timestamptz;
BEGIN
 IF message IS NULL OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$'
  OR payload IS NULL OR length(payload) NOT BETWEEN 100 AND 16384 THEN RETURN false; END IF;
 PERFORM set_config('forge.account_digest',digest,true);
 SELECT r.expires_at INTO expires FROM forge.account_password_resets r WHERE r.capability_hash=digest
  AND NOT r.consumed AND r.expires_at>clock_timestamp() FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM set_config('forge.account_message',message::text,true);
 INSERT INTO forge.account_message_delivery(id,reset_hash,encrypted_payload,expires_at)
 VALUES(message,digest,payload,expires);
 RETURN true;
END $$;

CREATE FUNCTION forge.account_claim_message(message uuid,lease uuid) RETURNS text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE item record;
BEGIN
 IF message IS NULL OR lease IS NULL THEN RETURN NULL; END IF;
 PERFORM set_config('forge.account_message',message::text,true);
 SELECT * INTO item FROM forge.account_message_delivery d WHERE d.id=message
  AND d.state IN ('pending','failed') AND d.attempts<3 AND d.expires_at>clock_timestamp()
  AND (d.lease_until IS NULL OR d.lease_until<=clock_timestamp()) FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF item.invitation_id IS NOT NULL THEN
  PERFORM set_config('forge.enrollment_invite',item.invitation_id::text,true);
  -- Only a matching, live pending intent can be dispatched. Digest is read from
  -- the owning invitation via the organization scope retained with the job.
  PERFORM set_config('forge.organization',item.organization_id::text,true);
  PERFORM 1 FROM forge.account_invitations i WHERE i.id=item.invitation_id
   AND i.state='pending' AND i.expires_at>clock_timestamp();
 ELSE
  PERFORM set_config('forge.account_digest',item.reset_hash,true);
  PERFORM 1 FROM forge.account_password_resets r WHERE r.capability_hash=item.reset_hash
   AND NOT r.consumed AND r.expires_at>clock_timestamp();
 END IF;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE forge.account_message_delivery SET attempts=attempts+1,state='pending',
  lease_token=lease,lease_until=clock_timestamp()+interval '30 seconds',updated_at=clock_timestamp() WHERE id=message;
 RETURN item.encrypted_payload;
END $$;

CREATE FUNCTION forge.account_finish_message(message uuid,lease uuid,delivered boolean) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF delivered IS NULL OR lease IS NULL THEN RETURN false; END IF;
 PERFORM set_config('forge.account_message',message::text,true);
 UPDATE forge.account_message_delivery SET state=CASE WHEN delivered THEN 'delivered' ELSE 'failed' END,
  lease_token=NULL,lease_until=NULL,updated_at=clock_timestamp()
  WHERE id=message AND state='pending' AND attempts>0 AND lease_token=lease AND lease_until>clock_timestamp();
 RETURN FOUND;
END $$;

RESET ROLE;
GRANT CREATE ON SCHEMA forge TO forge_enrollment_authority;
DO $$ DECLARE f record; BEGIN
 FOR f IN SELECT p.oid::regprocedure AS signature,p.proname FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='forge'
 AND p.proname IN ('account_lock','account_begin_login','account_finish_login','account_validate_session',
 'account_logout','account_disable','account_request_reset','account_consume_reset',
 'account_queue_message','account_queue_reset_message','account_claim_message','account_finish_message') LOOP
  EXECUTE format('ALTER FUNCTION %s OWNER TO forge_enrollment_authority',f.signature);
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
  IF f.proname<>'account_lock' THEN
   EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO forge_account_service',f.signature);
  END IF;
 END LOOP;
END $$;
REVOKE CREATE ON SCHEMA forge FROM forge_enrollment_authority;
COMMIT;
