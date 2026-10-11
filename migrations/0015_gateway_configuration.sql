-- Opt-in central gateway configuration; never applied to an existing demo implicitly.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_gateway_service NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_gateway_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_gateway_service',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_gateway_service,forge_gateway_authority;
CREATE TABLE forge.organization_gateways (
 organization_id uuid PRIMARY KEY REFERENCES forge.organizations(id),
 revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9223372036854775806),
 binding_id uuid NOT NULL UNIQUE,
 endpoint text NOT NULL CHECK(endpoint='https://ia.prometheonlab.com'),
 encrypted_key text NOT NULL CHECK(length(encrypted_key) BETWEEN 100 AND 12288),
 updated_by uuid NOT NULL REFERENCES forge.identities(id),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE forge.gateway_configuration_audit (
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 revision bigint NOT NULL,
 actor_id uuid NOT NULL REFERENCES forge.identities(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,revision)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['organization_gateways','gateway_configuration_audit'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE ON forge.%I TO forge_gateway_authority',t);
  EXECUTE format('CREATE POLICY gateway_scope ON forge.%I TO forge_gateway_authority USING (organization_id=forge.enrollment_uuid(''forge.organization'')) WITH CHECK (organization_id=forge.enrollment_uuid(''forge.organization''))',t);
 END LOOP;
END $$;
-- Resolve/lock existing membership through its established RLS authority.
-- Avoid granting the new authority direct access to identity/business tables.
CREATE FUNCTION forge.gateway_resolve_admin(org uuid,account uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid;
BEGIN
 PERFORM set_config('forge.organization',org::text,true);
 SELECT m.id INTO member FROM forge.memberships m
  WHERE m.organization_id=org AND m.identity_id=account AND m.status='active';
 RETURN forge.enrollment_lock_admin(org,member,'forge',
  'urn:prometheon:forge:accounts:v1',account::text);
END $$;
RESET ROLE;
ALTER FUNCTION forge.gateway_resolve_admin(uuid,uuid) OWNER TO forge_enrollment_authority;
REVOKE ALL ON FUNCTION forge.gateway_resolve_admin(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),
 forge.gateway_resolve_admin(uuid,uuid),forge.account_validate_session(text)
 TO forge_gateway_authority;
SET LOCAL ROLE forge_migrator;

CREATE FUNCTION forge.gateway_lock_admin(digest text,org uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; locked uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR org IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 PERFORM set_config('forge.organization',org::text,true);
 locked:=forge.gateway_resolve_admin(org,account);
 IF locked IS DISTINCT FROM account THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 RETURN account;
END $$;

CREATE FUNCTION forge.gateway_read(digest text,org uuid)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 RETURN QUERY SELECT g.revision,g.binding_id,g.endpoint,g.encrypted_key
  FROM forge.organization_gateways g WHERE g.organization_id=org;
END $$;

CREATE FUNCTION forge.gateway_save(digest text,org uuid,expected bigint,binding uuid,payload text)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.gateway_lock_admin(digest,org);
 IF expected IS NULL OR expected<0 OR expected>9223372036854775805
  OR binding IS NULL OR payload IS NULL OR length(payload) NOT BETWEEN 100 AND 12288 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 SELECT g.revision INTO current_revision FROM forge.organization_gateways g
  WHERE g.organization_id=org FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
 END IF;
 INSERT INTO forge.organization_gateways(organization_id,revision,binding_id,endpoint,encrypted_key,updated_by)
 VALUES(org,expected+1,binding,'https://ia.prometheonlab.com',payload,actor)
 ON CONFLICT(organization_id) DO UPDATE SET revision=excluded.revision,
  binding_id=excluded.binding_id,encrypted_key=excluded.encrypted_key,
  updated_by=excluded.updated_by,updated_at=clock_timestamp();
 INSERT INTO forge.gateway_configuration_audit(organization_id,revision,actor_id)
 VALUES(org,expected+1,actor);
 RETURN QUERY SELECT g.revision,g.binding_id,g.endpoint,g.encrypted_key
  FROM forge.organization_gateways g WHERE g.organization_id=org;
END $$;
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
RESET ROLE;
DO $$ DECLARE f record; BEGIN
 FOR f IN SELECT p.oid::regprocedure::text AS signature,p.proname
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='forge' AND p.proname IN ('gateway_lock_admin','gateway_read','gateway_save') LOOP
  EXECUTE format('ALTER FUNCTION %s OWNER TO forge_gateway_authority',f.signature);
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
  IF f.proname<>'gateway_lock_admin' THEN
   EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO forge_gateway_service',f.signature);
  END IF;
 END LOOP;
END $$;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
COMMIT;
