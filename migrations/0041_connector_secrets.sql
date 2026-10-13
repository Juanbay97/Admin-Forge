-- Connector broker storage: sealed credentials and grants, single-use OAuth states, the broker role pair and every broker
-- SECURITY DEFINER function. Additive and forward-only.
-- * forge_broker_authority (NOLOGIN) owns the functions; forge_broker_service (the 8th LOGIN pool) holds no table privilege and only
--   EXECUTEs them. The secrets are reachable only through this authority under row security (the capability role cannot read them).
-- * Org-level credentials (an API key or an OAuth client app) are written by a company administrator, write-only: the functions return
--   status, a last-four hint and the revision, never the sealed value. A NULL organization is the platform's default OAuth app.
-- * Per-member grants hold the sealed OAuth token bundle. Writes are compare-and-swap on the revision (CAP_CONFLICT -> BROKER_CONFLICT):
--   an advisory lock cannot span the provider round trip under the 5 s statement timeout, so refresh single-flight is the broker's own
--   lock plus this revision check.
-- * OAuth states are stored as a hash, single use: ``broker_oauth_take`` consumes the state (no session: the unguessable state is the
--   capability), ``broker_oauth_complete`` stores the grant only for a taken, uncompleted state.
-- * A membership leaving ``active`` deletes that member's grants and states in the same transaction (the revoke hook).
-- * Calls are audited as metadata only through the governance invocation log (source ``broker``); credential and connection changes
--   append to the governance change audit.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_broker_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_broker_service NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_broker_service',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_broker_authority,forge_broker_service;

ALTER TABLE forge.capability_change_audit DROP CONSTRAINT capability_change_audit_action_check;
ALTER TABLE forge.capability_change_audit ADD CONSTRAINT capability_change_audit_action_check CHECK(action IN
 ('catalog.created','catalog.updated','platform.policy_set','company.policy_set','org.setting_set','org.setting_cleared',
  'connector.credential_set','connector.credential_cleared','connector.connected','connector.disconnected'));

CREATE TABLE forge.connector_credentials (
 organization_id uuid REFERENCES forge.organizations(id),
 capability_id text NOT NULL REFERENCES forge.capability_catalog(id) CHECK(capability_id ~ '^connector:'),
 kind text NOT NULL CHECK(kind IN ('api_key','oauth_client')),
 sealed text NOT NULL CHECK(length(sealed) BETWEEN 80 AND 16384),
 hint text CHECK(hint IS NULL OR hint ~ '^[!-~]{4}$'),
 revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9223372036854775806),
 updated_by uuid REFERENCES forge.owned_accounts(id),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX connector_credentials_org ON forge.connector_credentials(organization_id,capability_id) WHERE organization_id IS NOT NULL;
CREATE UNIQUE INDEX connector_credentials_platform ON forge.connector_credentials(capability_id) WHERE organization_id IS NULL;

CREATE TABLE forge.connector_grants (
 organization_id uuid NOT NULL,
 membership_id uuid NOT NULL,
 capability_id text NOT NULL REFERENCES forge.capability_catalog(id) CHECK(capability_id ~ '^connector:'),
 sealed text NOT NULL CHECK(length(sealed) BETWEEN 80 AND 16384),
 revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9223372036854775806),
 status text NOT NULL CHECK(status IN ('connected','reauth_required')),
 access_expires_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,membership_id,capability_id),
 FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id)
);

CREATE TABLE forge.connector_oauth_states (
 state_hash text PRIMARY KEY CHECK(state_hash ~ '^[0-9a-f]{64}$'),
 organization_id uuid NOT NULL,
 membership_id uuid NOT NULL,
 account_id uuid NOT NULL,
 capability_id text NOT NULL REFERENCES forge.capability_catalog(id) CHECK(capability_id ~ '^connector:'),
 sealed_verifier text NOT NULL CHECK(length(sealed_verifier) BETWEEN 80 AND 4096),
 expires_at timestamptz NOT NULL,
 taken_at timestamptz,
 completed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id)
);
CREATE INDEX connector_oauth_states_by_member ON forge.connector_oauth_states(organization_id,membership_id);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['connector_credentials','connector_grants','connector_oauth_states'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service,forge_capability_service,forge_broker_service',t);
 END LOOP;
END $$;
CREATE POLICY broker_scope ON forge.connector_credentials TO forge_broker_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization') OR (organization_id IS NULL AND current_setting('forge.broker_platform',true)='1'))
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization') OR (organization_id IS NULL AND current_setting('forge.broker_platform',true)='1'));
CREATE POLICY broker_scope ON forge.connector_grants TO forge_broker_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization')) WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY broker_scope ON forge.connector_oauth_states TO forge_broker_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization') OR current_setting('forge.broker_state',true)='1')
 WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization'));
GRANT SELECT,INSERT,UPDATE,DELETE ON forge.connector_credentials,forge.connector_grants,forge.connector_oauth_states TO forge_broker_authority;
RESET ROLE;

GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),forge.account_validate_session(text),forge.platform_lock_owner(text,boolean),
 forge.cap_lock_member(text,uuid),forge.cap_lock_admin(text,uuid),forge.cap_layers(uuid),
 forge.cap_audit(text,uuid,uuid,text,text,text,text),
 forge.cap_invocation_record_broker(uuid,uuid,uuid,text,text,integer,text,text,bigint,bigint,integer) TO forge_broker_authority;
GRANT CREATE ON SCHEMA forge TO forge_capability_authority;
SET LOCAL ROLE forge_capability_authority;
-- The public (non-secret) catalog attributes of one connector, for the broker role that cannot read the catalog table.
CREATE FUNCTION forge.cap_connector_meta(cid text) RETURNS TABLE(id text,credential_locus text,attributes jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT c.id,c.credential_locus,c.attributes FROM forge.capability_catalog c WHERE c.id=cid AND c.kind='connector'
$$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_capability_authority;
REVOKE ALL ON FUNCTION forge.cap_connector_meta(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.cap_connector_meta(text) TO forge_broker_authority;
GRANT CREATE ON SCHEMA forge TO forge_broker_authority;
SET LOCAL ROLE forge_broker_authority;

-- The member's view: every connector with its layers, public attributes, credential presence and the member's connection state.
CREATE FUNCTION forge.broker_status(digest text,org uuid)
RETURNS TABLE(capability_id text,attributes jsonb,credential_locus text,default_state text,min_sandbox_level integer,platform_state text,
 platform_lock text,company_state text,company_lock text,org_enabled boolean,credential_scope text,credential_kind text,grant_status text,
 access_expires_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 PERFORM set_config('forge.organization',org::text,true);
 PERFORM set_config('forge.broker_platform','1',true);
 RETURN QUERY SELECT l.id,m.attributes,m.credential_locus,l.default_state,l.min_sandbox_level,l.platform_state,l.platform_lock,
   l.company_state,l.company_lock,l.org_enabled,
   CASE WHEN oc.capability_id IS NOT NULL THEN 'org' WHEN pc.capability_id IS NOT NULL THEN 'platform' END,
   coalesce(oc.kind,pc.kind),g.status,g.access_expires_at
  FROM forge.cap_layers(org) l
  JOIN forge.cap_connector_meta(l.id) m ON true
  LEFT JOIN forge.connector_credentials oc ON oc.organization_id=org AND oc.capability_id=l.id
  LEFT JOIN forge.connector_credentials pc ON pc.organization_id IS NULL AND pc.capability_id=l.id
  LEFT JOIN forge.connector_grants g ON g.organization_id=org AND g.membership_id=member AND g.capability_id=l.id
  WHERE l.kind='connector' ORDER BY l.id;
 PERFORM set_config('forge.broker_platform','',true);
END $$;

-- Everything one brokered call needs, in one statement under one snapshot: the member, the layers, the attributes, the credential
-- sealed values (opened by the application, in memory only) and the grant.
CREATE FUNCTION forge.broker_context(digest text,org uuid,cid text)
RETURNS TABLE(membership_id uuid,attributes jsonb,credential_locus text,default_state text,min_sandbox_level integer,platform_state text,
 platform_lock text,company_state text,company_lock text,org_enabled boolean,credential_scope text,credential_kind text,credential_sealed text,
 credential_revision bigint,grant_status text,grant_sealed text,grant_revision bigint,access_expires_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 IF cid IS NULL OR cid !~ '^connector:' THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_NOT_FOUND'; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 PERFORM set_config('forge.broker_platform','1',true);
 RETURN QUERY SELECT member,m.attributes,m.credential_locus,l.default_state,l.min_sandbox_level,l.platform_state,l.platform_lock,
   l.company_state,l.company_lock,l.org_enabled,
   CASE WHEN oc.capability_id IS NOT NULL THEN 'org' WHEN pc.capability_id IS NOT NULL THEN 'platform' END,
   coalesce(oc.kind,pc.kind),coalesce(oc.sealed,pc.sealed),coalesce(oc.revision,pc.revision),g.status,g.sealed,g.revision,g.access_expires_at
  FROM forge.cap_layers(org) l
  JOIN forge.cap_connector_meta(l.id) m ON true
  LEFT JOIN forge.connector_credentials oc ON oc.organization_id=org AND oc.capability_id=l.id
  LEFT JOIN forge.connector_credentials pc ON pc.organization_id IS NULL AND pc.capability_id=l.id
  LEFT JOIN forge.connector_grants g ON g.organization_id=org AND g.membership_id=member AND g.capability_id=l.id
  WHERE l.id=cid;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_NOT_FOUND'; END IF;
 PERFORM set_config('forge.broker_platform','',true);
END $$;

-- A company administrator's write-only credential: expected 0 creates, N updates; never returns the sealed value.
CREATE FUNCTION forge.broker_credential_save(digest text,org uuid,cid text,credential_kind text,expected bigint,sealed_value text,hint_value text)
RETURNS TABLE(revision bigint,hint text,kind text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.cap_lock_admin(digest,org);
 IF expected IS NULL OR expected<0 OR credential_kind IS NULL OR sealed_value IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END IF;
 PERFORM 1 FROM forge.cap_connector_meta(cid) m WHERE m.credential_locus='server';
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_NOT_FOUND'; END IF;
 SELECT c.revision INTO current_revision FROM forge.connector_credentials c WHERE c.organization_id=org AND c.capability_id=cid FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_CONFLICT'; END IF;
 BEGIN
  INSERT INTO forge.connector_credentials(organization_id,capability_id,kind,sealed,hint,revision,updated_by)
  VALUES(org,cid,credential_kind,sealed_value,hint_value,expected+1,actor)
  ON CONFLICT(organization_id,capability_id) WHERE organization_id IS NOT NULL DO UPDATE SET kind=excluded.kind,sealed=excluded.sealed,
   hint=excluded.hint,revision=excluded.revision,updated_by=excluded.updated_by,updated_at=clock_timestamp();
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END;
 PERFORM forge.cap_audit('org',org,actor,'connector.credential_set',cid,
  CASE WHEN expected>0 THEN 'r'||expected END,'r'||(expected+1));
 RETURN QUERY SELECT c.revision,c.hint,c.kind FROM forge.connector_credentials c WHERE c.organization_id=org AND c.capability_id=cid;
END $$;

CREATE FUNCTION forge.broker_credential_clear(digest text,org uuid,cid text,expected bigint) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.cap_lock_admin(digest,org);
 SELECT c.revision INTO current_revision FROM forge.connector_credentials c WHERE c.organization_id=org AND c.capability_id=cid FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF current_revision IS DISTINCT FROM expected THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_CONFLICT'; END IF;
 DELETE FROM forge.connector_credentials c WHERE c.organization_id=org AND c.capability_id=cid;
 PERFORM forge.cap_audit('org',org,actor,'connector.credential_cleared',cid,'r'||expected,NULL);
 RETURN true;
END $$;

-- Status of the company's credentials (and whether the platform default exists), for the administrator; no secret material.
CREATE FUNCTION forge.broker_credential_status(digest text,org uuid)
RETURNS TABLE(capability_id text,org_kind text,org_revision bigint,org_hint text,platform_kind text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.cap_lock_admin(digest,org);
 PERFORM set_config('forge.broker_platform','1',true);
 RETURN QUERY SELECT l.id,oc.kind,oc.revision,oc.hint,pc.kind FROM forge.cap_layers(org) l
  LEFT JOIN forge.connector_credentials oc ON oc.organization_id=org AND oc.capability_id=l.id
  LEFT JOIN forge.connector_credentials pc ON pc.organization_id IS NULL AND pc.capability_id=l.id
  WHERE l.kind='connector' AND (oc.capability_id IS NOT NULL OR pc.capability_id IS NOT NULL) ORDER BY l.id;
 PERFORM set_config('forge.broker_platform','',true);
END $$;

-- The platform's default OAuth app for a connector (NULL organization); a company's own credential overrides it.
CREATE FUNCTION forge.broker_platform_credential_save(digest text,cid text,credential_kind text,expected bigint,sealed_value text,hint_value text)
RETURNS TABLE(revision bigint,hint text,kind text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF expected IS NULL OR expected<0 OR credential_kind IS NULL OR sealed_value IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END IF;
 PERFORM 1 FROM forge.cap_connector_meta(cid) m WHERE m.credential_locus='server';
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_NOT_FOUND'; END IF;
 PERFORM set_config('forge.broker_platform','1',true);
 SELECT c.revision INTO current_revision FROM forge.connector_credentials c WHERE c.organization_id IS NULL AND c.capability_id=cid FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_CONFLICT'; END IF;
 BEGIN
  INSERT INTO forge.connector_credentials(organization_id,capability_id,kind,sealed,hint,revision,updated_by)
  VALUES(NULL,cid,credential_kind,sealed_value,hint_value,expected+1,actor)
  ON CONFLICT(capability_id) WHERE organization_id IS NULL DO UPDATE SET kind=excluded.kind,sealed=excluded.sealed,hint=excluded.hint,
   revision=excluded.revision,updated_by=excluded.updated_by,updated_at=clock_timestamp();
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END;
 PERFORM forge.cap_audit('platform',NULL,actor,'connector.credential_set',cid,CASE WHEN expected>0 THEN 'r'||expected END,'r'||(expected+1));
 RETURN QUERY SELECT c.revision,c.hint,c.kind FROM forge.connector_credentials c WHERE c.organization_id IS NULL AND c.capability_id=cid;
 PERFORM set_config('forge.broker_platform','',true);
END $$;

-- The credential revision the platform default currently has (0 when none): the application seals the next revision with it.
CREATE FUNCTION forge.broker_platform_credential_revision(digest text,cid text) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE found_revision bigint;
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM set_config('forge.broker_platform','1',true);
 SELECT c.revision INTO found_revision FROM forge.connector_credentials c WHERE c.organization_id IS NULL AND c.capability_id=cid;
 PERFORM set_config('forge.broker_platform','',true);
 RETURN coalesce(found_revision,0);
END $$;

CREATE FUNCTION forge.broker_credential_revision(digest text,org uuid,cid text) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE found_revision bigint;
BEGIN
 PERFORM forge.cap_lock_admin(digest,org);
 SELECT c.revision INTO found_revision FROM forge.connector_credentials c WHERE c.organization_id=org AND c.capability_id=cid;
 RETURN coalesce(found_revision,0);
END $$;

-- OAuth: start (member session) stores the hashed single-use state with the sealed PKCE verifier.
CREATE FUNCTION forge.broker_oauth_start(digest text,org uuid,cid text,hashed text,sealed_value text,ttl integer) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; account uuid;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 account:=forge.account_validate_session(digest);
 IF hashed IS NULL OR sealed_value IS NULL OR ttl IS NULL OR ttl NOT BETWEEN 60 AND 600 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END IF;
 PERFORM 1 FROM forge.cap_connector_meta(cid);
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_NOT_FOUND'; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 DELETE FROM forge.connector_oauth_states s WHERE s.organization_id=org AND s.membership_id=member
  AND (s.expires_at<clock_timestamp()-interval '1 hour' OR s.completed_at IS NOT NULL);
 IF (SELECT count(*) FROM forge.connector_oauth_states s WHERE s.organization_id=org AND s.membership_id=member
     AND s.completed_at IS NULL AND s.expires_at>clock_timestamp())>=5 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_LIMIT';
 END IF;
 BEGIN
  INSERT INTO forge.connector_oauth_states(state_hash,organization_id,membership_id,account_id,capability_id,sealed_verifier,expires_at)
  VALUES(hashed,org,member,account,cid,sealed_value,clock_timestamp()+make_interval(secs=>ttl));
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END;
END $$;

-- OAuth callback, step 1 (no session): consume a valid state once and return what the exchange needs. Any other state is the same refusal.
CREATE FUNCTION forge.broker_oauth_take(hashed text)
RETURNS TABLE(organization_id uuid,membership_id uuid,capability_id text,sealed_verifier text,grant_revision bigint,attributes jsonb,
 default_state text,min_sandbox_level integer,platform_state text,platform_lock text,company_state text,company_lock text,org_enabled boolean,
 credential_scope text,credential_kind text,credential_sealed text,credential_revision bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s forge.connector_oauth_states%ROWTYPE; current_revision bigint;
BEGIN
 IF hashed IS NULL OR hashed !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_DENIED'; END IF;
 PERFORM set_config('forge.broker_state','1',true);
 SELECT * INTO s FROM forge.connector_oauth_states t WHERE t.state_hash=hashed FOR UPDATE;
 IF NOT FOUND OR s.taken_at IS NOT NULL OR s.completed_at IS NOT NULL OR s.expires_at<=clock_timestamp() THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_DENIED';
 END IF;
 PERFORM set_config('forge.broker_state','',true);
 PERFORM set_config('forge.organization',s.organization_id::text,true);
 UPDATE forge.connector_oauth_states t SET taken_at=clock_timestamp() WHERE t.state_hash=hashed;
 SELECT g.revision INTO current_revision FROM forge.connector_grants g
  WHERE g.organization_id=s.organization_id AND g.membership_id=s.membership_id AND g.capability_id=s.capability_id;
 -- The exchange has no session, so the state also carries what the exchange needs: the connector's attributes, the layers (a connector
 -- turned off since the start is refused by the application) and the client credential, resolved exactly as for a call.
 PERFORM set_config('forge.broker_platform','1',true);
 RETURN QUERY SELECT s.organization_id,s.membership_id,s.capability_id,s.sealed_verifier,coalesce(current_revision,0),m.attributes,
   l.default_state,l.min_sandbox_level,l.platform_state,l.platform_lock,l.company_state,l.company_lock,l.org_enabled,
   CASE WHEN oc.capability_id IS NOT NULL THEN 'org' WHEN pc.capability_id IS NOT NULL THEN 'platform' END,
   coalesce(oc.kind,pc.kind),coalesce(oc.sealed,pc.sealed),coalesce(oc.revision,pc.revision)
  FROM forge.cap_layers(s.organization_id) l
  JOIN forge.cap_connector_meta(l.id) m ON true
  LEFT JOIN forge.connector_credentials oc ON oc.organization_id=s.organization_id AND oc.capability_id=l.id
  LEFT JOIN forge.connector_credentials pc ON pc.organization_id IS NULL AND pc.capability_id=l.id
  WHERE l.id=s.capability_id;
 PERFORM set_config('forge.broker_platform','',true);
END $$;

-- Step 2 (no session): store the grant for a state that was taken and not completed; compare-and-swap on the grant revision.
CREATE FUNCTION forge.broker_oauth_complete(hashed text,expected bigint,sealed_value text,expires timestamptz) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s forge.connector_oauth_states%ROWTYPE; current_revision bigint;
BEGIN
 IF hashed IS NULL OR hashed !~ '^[0-9a-f]{64}$' OR expected IS NULL OR expected<0 OR sealed_value IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_DENIED';
 END IF;
 PERFORM set_config('forge.broker_state','1',true);
 SELECT * INTO s FROM forge.connector_oauth_states t WHERE t.state_hash=hashed FOR UPDATE;
 IF NOT FOUND OR s.taken_at IS NULL OR s.completed_at IS NOT NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_DENIED'; END IF;
 PERFORM set_config('forge.broker_state','',true);
 PERFORM set_config('forge.organization',s.organization_id::text,true);
 SELECT g.revision INTO current_revision FROM forge.connector_grants g
  WHERE g.organization_id=s.organization_id AND g.membership_id=s.membership_id AND g.capability_id=s.capability_id FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_CONFLICT'; END IF;
 BEGIN
  INSERT INTO forge.connector_grants(organization_id,membership_id,capability_id,sealed,revision,status,access_expires_at)
  VALUES(s.organization_id,s.membership_id,s.capability_id,sealed_value,expected+1,'connected',expires)
  ON CONFLICT(organization_id,membership_id,capability_id) DO UPDATE SET sealed=excluded.sealed,revision=excluded.revision,
   status='connected',access_expires_at=excluded.access_expires_at,updated_at=clock_timestamp();
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END;
 UPDATE forge.connector_oauth_states t SET completed_at=clock_timestamp() WHERE t.state_hash=hashed;
 PERFORM forge.cap_audit('org',s.organization_id,s.account_id,'connector.connected',s.capability_id,NULL,'connected');
 RETURN expected+1;
END $$;

-- A refresh result or a reauthorization flag, on behalf of the member whose session is valid; compare-and-swap on the revision.
CREATE FUNCTION forge.broker_grant_update(digest text,org uuid,cid text,expected bigint,sealed_value text,expires timestamptz,new_status text) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; current_revision bigint;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 PERFORM set_config('forge.organization',org::text,true);
 IF expected IS NULL OR expected<1 OR new_status NOT IN ('connected','reauth_required') OR (new_status='connected' AND sealed_value IS NULL) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END IF;
 SELECT g.revision INTO current_revision FROM forge.connector_grants g
  WHERE g.organization_id=org AND g.membership_id=member AND g.capability_id=cid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_NOT_FOUND'; END IF;
 IF current_revision<>expected THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_CONFLICT'; END IF;
 BEGIN
  UPDATE forge.connector_grants g SET sealed=coalesce(sealed_value,g.sealed),revision=g.revision+CASE WHEN sealed_value IS NULL THEN 0 ELSE 1 END,
   status=new_status,access_expires_at=CASE WHEN sealed_value IS NULL THEN g.access_expires_at ELSE expires END,updated_at=clock_timestamp()
   WHERE g.organization_id=org AND g.membership_id=member AND g.capability_id=cid;
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BROKER_INVALID';
 END;
 RETURN expected+CASE WHEN sealed_value IS NULL THEN 0 ELSE 1 END;
END $$;

-- Disconnect: delete the member's grant (the tokens are destroyed) and audit it; the sealed value is returned once so the application
-- can revoke it at the provider when the connector has a revocation endpoint.
CREATE FUNCTION forge.broker_grant_delete(digest text,org uuid,cid text)
RETURNS TABLE(deleted_revision bigint,deleted_sealed text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; account uuid; gone forge.connector_grants%ROWTYPE;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 account:=forge.account_validate_session(digest);
 PERFORM set_config('forge.organization',org::text,true);
 DELETE FROM forge.connector_grants g WHERE g.organization_id=org AND g.membership_id=member AND g.capability_id=cid RETURNING * INTO gone;
 IF NOT FOUND THEN RETURN; END IF;
 PERFORM forge.cap_audit('org',org,account,'connector.disconnected',cid,'connected',NULL);
 RETURN QUERY SELECT gone.revision,gone.sealed;
END $$;

-- One metadata row per brokered call (never a body or a header), through the governance invocation log with source 'broker'.
CREATE FUNCTION forge.broker_log_call(org uuid,member uuid,event uuid,cid text,result text,took integer,rpc text,tool text,sent bigint,
 received bigint,status integer) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 RETURN forge.cap_invocation_record_broker(org,member,event,cid,result,took,rpc,tool,sent,received,status);
END $$;

-- The revoke hook: a membership that leaves 'active' loses its grants and pending states at once.
CREATE FUNCTION forge.broker_member_revoked() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM set_config('forge.organization',NEW.organization_id::text,true);
 DELETE FROM forge.connector_grants g WHERE g.organization_id=NEW.organization_id AND g.membership_id=NEW.id;
 DELETE FROM forge.connector_oauth_states s WHERE s.organization_id=NEW.organization_id AND s.membership_id=NEW.id;
 RETURN NEW;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_broker_authority;
GRANT EXECUTE ON FUNCTION forge.broker_member_revoked() TO forge_migrator;
SET LOCAL ROLE forge_migrator;
CREATE TRIGGER broker_member_revoked AFTER UPDATE OF status ON forge.memberships FOR EACH ROW
 WHEN (OLD.status='active' AND NEW.status<>'active') EXECUTE FUNCTION forge.broker_member_revoked();
RESET ROLE;
REVOKE ALL ON FUNCTION forge.broker_status(text,uuid),forge.broker_context(text,uuid,text),
 forge.broker_credential_save(text,uuid,text,text,bigint,text,text),forge.broker_credential_clear(text,uuid,text,bigint),
 forge.broker_credential_status(text,uuid),forge.broker_platform_credential_save(text,text,text,bigint,text,text),
 forge.broker_platform_credential_revision(text,text),forge.broker_credential_revision(text,uuid,text),
 forge.broker_oauth_start(text,uuid,text,text,text,integer),forge.broker_oauth_take(text),
 forge.broker_oauth_complete(text,bigint,text,timestamptz),forge.broker_grant_update(text,uuid,text,bigint,text,timestamptz,text),
 forge.broker_grant_delete(text,uuid,text),forge.broker_log_call(uuid,uuid,uuid,text,text,integer,text,text,bigint,bigint,integer),
 forge.broker_member_revoked() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.broker_status(text,uuid),forge.broker_context(text,uuid,text),
 forge.broker_credential_save(text,uuid,text,text,bigint,text,text),forge.broker_credential_clear(text,uuid,text,bigint),
 forge.broker_credential_status(text,uuid),forge.broker_platform_credential_save(text,text,text,bigint,text,text),
 forge.broker_platform_credential_revision(text,text),forge.broker_credential_revision(text,uuid,text),
 forge.broker_oauth_start(text,uuid,text,text,text,integer),forge.broker_oauth_take(text),
 forge.broker_oauth_complete(text,bigint,text,timestamptz),forge.broker_grant_update(text,uuid,text,bigint,text,timestamptz,text),
 forge.broker_grant_delete(text,uuid,text),forge.broker_log_call(uuid,uuid,uuid,text,text,integer,text,text,bigint,bigint,integer)
 TO forge_broker_service;
COMMIT;
