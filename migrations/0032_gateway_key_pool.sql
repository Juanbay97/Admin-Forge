-- Platform-owned gateway key pool. Additive and forward-only.
-- * gateway_keys: keys belong to the platform, not to a company. Key text exists only as an opaque sealed value (the
--   application seals it with a v2 payload bound to the key id, revision and origin) plus a last-4 hint; no function
--   returns it to a platform caller. A key row may be a placeholder (no sealed value yet); it is never routed.
-- * organization_gateway_keys: which keys a company may use, with a unique priority and an active flag.
-- * organization_gateway_profiles: one stable catalog binding per company (binding_id, revision) that outlives key
--   rotation and reordering, plus the platform-set model ceiling (NULL = unrestricted, only ever written by the
--   legacy backfill of a later migration; a profile created by assignment starts at the empty, deny-everything list).
-- * The database no longer pins an origin for pool keys: it keeps only the canonical-origin format check (as 0027) and the
--   deployment allow-list in the application is the authority.
-- Every platform function re-validates a fresh verified owner session first and writes its audit row in the same
-- transaction. The member-route authority (forge_gateway_authority) only reads the pool, scoped to one company.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.gateway_keys (
 id uuid PRIMARY KEY,
 label text NOT NULL UNIQUE CHECK(label ~ '^[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}$'),
 origin text NOT NULL CHECK(length(origin)<=255 AND (
  (origin ~ '^https://[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?$'
   AND origin !~ '^https://[0-9]+(\.[0-9]+){3}(:|$)')
  OR origin ~ '^http://127\.0\.0\.1:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$')),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 9223372036854775806),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
 encrypted_key text CHECK(encrypted_key IS NULL OR length(encrypted_key) BETWEEN 100 AND 12288),
 last4 text CHECK(last4 IS NULL OR last4 ~ '^[!-~]{1,4}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE forge.organization_gateway_profiles (
 organization_id uuid PRIMARY KEY REFERENCES forge.organizations(id),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 9223372036854775806),
 binding_id uuid NOT NULL UNIQUE,
 ceiling text[] CHECK(ceiling IS NULL OR cardinality(ceiling)<=500),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE forge.organization_gateway_keys (
 organization_id uuid NOT NULL REFERENCES forge.organization_gateway_profiles(organization_id),
 key_id uuid NOT NULL REFERENCES forge.gateway_keys(id),
 priority integer NOT NULL CHECK(priority BETWEEN 1 AND 1000),
 active boolean NOT NULL,
 assigned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,key_id),
 UNIQUE(organization_id,priority)
);

-- Who the audit row is about when it is not a company: the key. Never an email, a name or a secret.
ALTER TABLE forge.platform_audit_log ADD COLUMN subject_id uuid;
ALTER TABLE forge.platform_audit_log DROP CONSTRAINT platform_audit_log_action_check;
ALTER TABLE forge.platform_audit_log ADD CONSTRAINT platform_audit_log_action_check CHECK(action IN
 ('company.created','company.suspended','company.reactivated','company.branding_saved','owner.mfa_enrolled',
  'owner.mfa_recovery_used','gateway_key.created','gateway_key.rotated','gateway_key.status_changed',
  'company.gateway_assigned','company.model_access_set'));

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['gateway_keys','organization_gateway_profiles','organization_gateway_keys'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service',t);
  EXECUTE format('CREATE POLICY platform_scope ON forge.%I TO forge_platform_authority USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON forge.gateway_keys TO forge_platform_authority;
GRANT SELECT,INSERT,UPDATE ON forge.organization_gateway_profiles TO forge_platform_authority;
GRANT SELECT,INSERT,UPDATE,DELETE ON forge.organization_gateway_keys TO forge_platform_authority;
-- The member route reads one company's profile and assignments, and only the keys assigned to that company.
GRANT SELECT ON forge.gateway_keys,forge.organization_gateway_profiles,forge.organization_gateway_keys TO forge_gateway_authority;
CREATE POLICY pool_scope ON forge.organization_gateway_profiles FOR SELECT TO forge_gateway_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY pool_scope ON forge.organization_gateway_keys FOR SELECT TO forge_gateway_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization'));
CREATE POLICY pool_scope ON forge.gateway_keys FOR SELECT TO forge_gateway_authority
 USING(EXISTS(SELECT 1 FROM forge.organization_gateway_keys a
  WHERE a.key_id=gateway_keys.id AND a.organization_id=forge.enrollment_uuid('forge.organization')));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- Internal: the audit write with a subject (a key). The three-argument form stays as it is.
CREATE FUNCTION forge.platform_audit_write(actor uuid,act text,org uuid,subject uuid) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE written bigint;
BEGIN
 INSERT INTO forge.platform_audit_log(actor_id,action,organization_id,subject_id) VALUES(actor,act,org,subject)
  RETURNING id INTO written;
 RETURN written;
END $$;

-- Internal: one key as the finite metadata a platform caller may see (never the sealed value).
CREATE FUNCTION forge.platform_gateway_key_meta(kid uuid)
RETURNS TABLE(id uuid,label text,origin text,revision bigint,status text,has_key boolean,hint text,companies bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT k.id,k.label,k.origin,k.revision,k.status,k.encrypted_key IS NOT NULL,k.last4,
  (SELECT count(*) FROM forge.organization_gateway_keys a WHERE a.key_id=k.id)
 FROM forge.gateway_keys k WHERE k.id=kid
$$;

CREATE FUNCTION forge.platform_gateway_key_create(digest text,kid uuid,key_label text,key_origin text,sealed text,key_hint text)
RETURNS TABLE(id uuid,label text,origin text,revision bigint,status text,has_key boolean,hint text,companies bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF kid IS NULL OR key_label IS NULL OR key_origin IS NULL OR (sealed IS NULL)<>(key_hint IS NULL) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 BEGIN
  INSERT INTO forge.gateway_keys(id,label,origin,encrypted_key,last4) VALUES(kid,key_label,key_origin,sealed,key_hint);
 EXCEPTION
  WHEN unique_violation THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='KEY_CONFLICT';
  WHEN check_violation THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END;
 PERFORM forge.platform_audit_write(actor,'gateway_key.created',NULL,kid);
 RETURN QUERY SELECT * FROM forge.platform_gateway_key_meta(kid);
END $$;

CREATE FUNCTION forge.platform_gateway_key_list(digest text)
RETURNS TABLE(id uuid,label text,origin text,revision bigint,status text,has_key boolean,hint text,companies bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 RETURN QUERY SELECT m.* FROM forge.gateway_keys k,LATERAL forge.platform_gateway_key_meta(k.id) m ORDER BY k.label;
END $$;

-- Compare-and-swap on the revision; the new sealed value is bound to revision+1 by the caller.
CREATE FUNCTION forge.platform_gateway_key_rotate(digest text,kid uuid,expected bigint,sealed text,key_hint text)
RETURNS TABLE(id uuid,label text,origin text,revision bigint,status text,has_key boolean,hint text,companies bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF kid IS NULL OR expected IS NULL OR expected<1 OR expected>9223372036854775804 OR sealed IS NULL OR key_hint IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 SELECT k.revision INTO current_revision FROM forge.gateway_keys k WHERE k.id=kid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND'; END IF;
 IF current_revision<>expected THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT'; END IF;
 BEGIN
  UPDATE forge.gateway_keys k SET revision=expected+1,encrypted_key=sealed,last4=key_hint,updated_at=clock_timestamp() WHERE k.id=kid;
 EXCEPTION WHEN check_violation THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END;
 PERFORM forge.platform_audit_write(actor,'gateway_key.rotated',NULL,kid);
 RETURN QUERY SELECT * FROM forge.platform_gateway_key_meta(kid);
END $$;

-- Disable (turn_on=false) or enable; a repeat is a no-op without a second audit row.
CREATE FUNCTION forge.platform_gateway_key_set_status(digest text,kid uuid,turn_on boolean)
RETURNS TABLE(id uuid,label text,origin text,revision bigint,status text,has_key boolean,hint text,companies bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; was text; wanted text;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF kid IS NULL OR turn_on IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID'; END IF;
 wanted:=CASE WHEN turn_on THEN 'active' ELSE 'disabled' END;
 SELECT k.status INTO was FROM forge.gateway_keys k WHERE k.id=kid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND'; END IF;
 IF was<>wanted THEN
  UPDATE forge.gateway_keys k SET status=wanted,updated_at=clock_timestamp() WHERE k.id=kid;
  PERFORM forge.platform_audit_write(actor,'gateway_key.status_changed',NULL,kid);
 END IF;
 RETURN QUERY SELECT * FROM forge.platform_gateway_key_meta(kid);
END $$;

CREATE FUNCTION forge.platform_company_gateway_get(digest text,org uuid)
RETURNS TABLE(key_id uuid,label text,origin text,priority integer,active boolean,key_status text,has_key boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.organizations o WHERE o.id=org) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 RETURN QUERY SELECT a.key_id,k.label,k.origin,a.priority,a.active,k.status,k.encrypted_key IS NOT NULL
  FROM forge.organization_gateway_keys a JOIN forge.gateway_keys k ON k.id=a.key_id
  WHERE a.organization_id=org ORDER BY a.priority;
END $$;

-- The whole assignment list at once (replace): priorities are unique, keys must exist. The profile (the catalog
-- binding) is created on the first assignment and is never touched again, so rotation and reordering keep catalogs.
CREATE FUNCTION forge.platform_company_gateway_set(digest text,org uuid,entries jsonb)
RETURNS TABLE(key_id uuid,label text,origin text,priority integer,active boolean,key_status text,has_key boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.organizations o WHERE o.id=org) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 IF entries IS NULL OR jsonb_typeof(entries)<>'array' OR jsonb_array_length(entries)>16
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(entries) e WHERE jsonb_typeof(e)<>'object'
   OR (e-'key_id'-'priority'-'active')<>'{}'::jsonb OR NOT (e ?& ARRAY['key_id','priority','active'])
   OR jsonb_typeof(e->'key_id')<>'string' OR jsonb_typeof(e->'priority')<>'number' OR jsonb_typeof(e->'active')<>'boolean') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended('forge.gateway_profile:'||org::text,0));
  INSERT INTO forge.organization_gateway_profiles(organization_id,revision,binding_id,ceiling)
  VALUES(org,1,gen_random_uuid(),ARRAY[]::text[]) ON CONFLICT(organization_id) DO NOTHING;
  DELETE FROM forge.organization_gateway_keys a WHERE a.organization_id=org;
  INSERT INTO forge.organization_gateway_keys(organization_id,key_id,priority,active)
   SELECT org,(e->>'key_id')::uuid,(e->>'priority')::integer,(e->>'active')::boolean FROM jsonb_array_elements(entries) e;
 EXCEPTION WHEN unique_violation OR check_violation OR foreign_key_violation OR invalid_text_representation
  OR numeric_value_out_of_range THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END;
 PERFORM forge.platform_audit_write(actor,'company.gateway_assigned',org,NULL);
 RETURN QUERY SELECT a.key_id,k.label,k.origin,a.priority,a.active,k.status,k.encrypted_key IS NOT NULL
  FROM forge.organization_gateway_keys a JOIN forge.gateway_keys k ON k.id=a.key_id
  WHERE a.organization_id=org ORDER BY a.priority;
END $$;

-- The platform-set allowed upstream models of a company (no row = nothing configured = nothing allowed).
CREATE FUNCTION forge.platform_company_model_access_get(digest text,org uuid) RETURNS TABLE(models text[])
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.organizations o WHERE o.id=org) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 RETURN QUERY SELECT p.ceiling FROM forge.organization_gateway_profiles p WHERE p.organization_id=org;
END $$;

CREATE FUNCTION forge.platform_company_model_access_set(digest text,org uuid,models text[]) RETURNS text[]
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.organizations o WHERE o.id=org) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 IF models IS NULL OR cardinality(models)>500 OR coalesce(array_ndims(models),1)<>1
  OR EXISTS(SELECT 1 FROM unnest(models) m WHERE m IS NULL OR m !~ '^[!-~]{1,255}$')
  OR (SELECT count(DISTINCT m) FROM unnest(models) m)<>cardinality(models) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('forge.gateway_profile:'||org::text,0));
 INSERT INTO forge.organization_gateway_profiles(organization_id,revision,binding_id,ceiling)
 VALUES(org,1,gen_random_uuid(),models)
 ON CONFLICT(organization_id) DO UPDATE SET ceiling=excluded.ceiling,updated_at=clock_timestamp();
 PERFORM forge.platform_audit_write(actor,'company.model_access_set',org,NULL);
 RETURN models;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_audit_write(uuid,text,uuid,uuid),forge.platform_gateway_key_meta(uuid),
 forge.platform_gateway_key_create(text,uuid,text,text,text,text),forge.platform_gateway_key_list(text),
 forge.platform_gateway_key_rotate(text,uuid,bigint,text,text),forge.platform_gateway_key_set_status(text,uuid,boolean),
 forge.platform_company_gateway_get(text,uuid),forge.platform_company_gateway_set(text,uuid,jsonb),
 forge.platform_company_model_access_get(text,uuid),forge.platform_company_model_access_set(text,uuid,text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_gateway_key_create(text,uuid,text,text,text,text),forge.platform_gateway_key_list(text),
 forge.platform_gateway_key_rotate(text,uuid,bigint,text,text),forge.platform_gateway_key_set_status(text,uuid,boolean),
 forge.platform_company_gateway_get(text,uuid),forge.platform_company_gateway_set(text,uuid,jsonb),
 forge.platform_company_model_access_get(text,uuid),forge.platform_company_model_access_set(text,uuid,text[])
 TO forge_platform_service;
COMMIT;
