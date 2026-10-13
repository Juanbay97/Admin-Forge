-- Capability governance, storage 2/3: company overrides, organization-administrator settings, per-company epochs, the
-- append-only change audit and every governance SECURITY DEFINER function. Additive and forward-only.
-- * Layers: the platform default (0038), the per-company override the platform owner sets (state + force-off lock) and the
--   setting a company administrator writes. Resolution itself is application code; the database enforces who may write what.
-- * Every write re-validates the live session (a fresh verified platform owner through ``platform_lock_owner``, or an active
--   administrator of exactly that company), refuses a locked capability for administrators (CAP_LOCKED), bumps the epoch
--   and appends its audit row in the same transaction: a failed write leaves no audit row.
-- * The audit is append-only by privilege: the authority holds SELECT and INSERT only and no other role holds anything. It
--   stores who, what, which company, the before/after state words and when; never content. A NULL actor is the trusted
--   operator seed.
-- * Tenant tables answer to the ``forge.organization`` context a function sets; a function can open the whole audit only for
--   a platform owner (``forge.cap_platform``).
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.capability_company_overrides (
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 capability_id text NOT NULL REFERENCES forge.capability_catalog(id),
 state text CHECK(state IS NULL OR state IN ('on','off')),
 lock text NOT NULL DEFAULT 'none' CHECK(lock IN ('none','forced_off')),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,capability_id)
);
CREATE TABLE forge.capability_org_settings (
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 capability_id text NOT NULL REFERENCES forge.capability_catalog(id),
 enabled boolean NOT NULL,
 updated_by uuid NOT NULL REFERENCES forge.owned_accounts(id),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,capability_id)
);
CREATE TABLE forge.capability_org_epochs (
 organization_id uuid PRIMARY KEY REFERENCES forge.organizations(id),
 epoch bigint NOT NULL CHECK(epoch BETWEEN 2 AND 9223372036854775806)
);
CREATE TABLE forge.capability_change_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scope text NOT NULL CHECK(scope IN ('platform','org')),
 organization_id uuid REFERENCES forge.organizations(id),
 actor_id uuid REFERENCES forge.owned_accounts(id),
 action text NOT NULL CHECK(action IN ('catalog.created','catalog.updated','platform.policy_set','company.policy_set',
  'org.setting_set','org.setting_cleared')),
 target text NOT NULL CHECK(target ~ '^(tool|skill|connector|plugin|app):[a-z0-9][a-z0-9._-]{0,127}$'),
 before_state text CHECK(before_state IS NULL OR before_state ~ '^[a-z0-9_+]{1,64}$'),
 after_state text CHECK(after_state IS NULL OR after_state ~ '^[a-z0-9_+]{1,64}$'),
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((scope='platform' AND organization_id IS NULL) OR (scope='org' AND organization_id IS NOT NULL))
);
CREATE INDEX capability_change_audit_by_org ON forge.capability_change_audit(organization_id,id);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['capability_company_overrides','capability_org_settings','capability_org_epochs','capability_change_audit'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service,forge_capability_service',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['capability_company_overrides','capability_org_settings','capability_org_epochs'] LOOP
  EXECUTE format('CREATE POLICY capability_org_scope ON forge.%I TO forge_capability_authority USING(organization_id=forge.enrollment_uuid(''forge.organization'')) WITH CHECK(organization_id=forge.enrollment_uuid(''forge.organization''))',t);
 END LOOP;
END $$;
CREATE POLICY capability_audit_scope ON forge.capability_change_audit TO forge_capability_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization') OR current_setting('forge.cap_platform',true)='1')
 WITH CHECK(organization_id IS NOT DISTINCT FROM forge.enrollment_uuid('forge.organization') OR (organization_id IS NULL AND scope='platform'));
GRANT SELECT,INSERT,UPDATE ON forge.capability_company_overrides,forge.capability_org_epochs TO forge_capability_authority;
GRANT SELECT,INSERT,UPDATE,DELETE ON forge.capability_org_settings TO forge_capability_authority;
GRANT SELECT,INSERT ON forge.capability_change_audit TO forge_capability_authority;
RESET ROLE;

GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),forge.context_organization(),forge.context_ready(),
 forge.account_validate_session(text),forge.gateway_resolve_admin(uuid,uuid),forge.gateway_resolve_member(uuid,uuid),
 forge.platform_lock_owner(text,boolean) TO forge_capability_authority;
GRANT CREATE ON SCHEMA forge TO forge_capability_authority;
SET LOCAL ROLE forge_capability_authority;

-- Internal guards. Each ends the caller's transaction with one finite code when the actor is not who the operation needs.
CREATE FUNCTION forge.cap_lock_admin(digest text,org uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; locked uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR org IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_DENIED'; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 locked:=forge.gateway_resolve_admin(org,account);
 IF locked IS DISTINCT FROM account THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_DENIED'; END IF;
 RETURN account;
END $$;

CREATE FUNCTION forge.cap_lock_member(digest text,org uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; member uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR org IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_DENIED'; END IF;
 member:=forge.gateway_resolve_member(org,account);
 IF member IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_DENIED'; END IF;
 RETURN member;
END $$;

CREATE FUNCTION forge.cap_audit(kind text,org uuid,actor uuid,act text,target_id text,before_word text,after_word text) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 INSERT INTO forge.capability_change_audit(scope,organization_id,actor_id,action,target,before_state,after_state)
 VALUES(kind,org,actor,act,target_id,before_word,after_word);
END $$;

CREATE FUNCTION forge.cap_word(state text,lock text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT coalesce(state,'inherit')||CASE WHEN lock='forced_off' THEN '+forced_off' ELSE '' END
$$;

CREATE FUNCTION forge.cap_bump_platform() RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 INSERT INTO forge.capability_platform_epoch(singleton,epoch) VALUES(true,2)
 ON CONFLICT(singleton) DO UPDATE SET epoch=forge.capability_platform_epoch.epoch+1
$$;

CREATE FUNCTION forge.cap_bump_org(org uuid) RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 INSERT INTO forge.capability_org_epochs(organization_id,epoch) VALUES(org,2)
 ON CONFLICT(organization_id) DO UPDATE SET epoch=forge.capability_org_epochs.epoch+1
$$;

-- One catalog entry: expected 0 creates (a duplicate id is CAP_CONFLICT), expected N updates (a stale N is CAP_CONFLICT).
-- A no-op update changes nothing: no revision, no epoch, no audit row, which is what makes the seed idempotent.
CREATE FUNCTION forge.cap_catalog_put(digest text,cid text,expected bigint,entry jsonb)
RETURNS TABLE(id text,kind text,version text,risk text,is_base boolean,default_state text,min_sandbox_level integer,
 manifest_sha256 text,credential_locus text,declared_permissions text[],granted_permissions text[],revision bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; cur forge.capability_catalog%ROWTYPE; made forge.capability_catalog%ROWTYPE;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF cid IS NULL OR expected IS NULL OR expected<0 OR entry IS NULL OR jsonb_typeof(entry)<>'object' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END IF;
 SELECT * INTO cur FROM forge.capability_catalog c WHERE c.id=cid FOR UPDATE;
 IF expected=0 AND FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_CONFLICT'; END IF;
 IF expected>0 AND (NOT FOUND OR cur.revision<>expected) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_CONFLICT'; END IF;
 BEGIN
  made.id:=cid; made.kind:=split_part(cid,':',1);
  made.version:=entry->>'version'; made.risk:=entry->>'risk'; made.is_base:=(entry->>'is_base')::boolean;
  made.default_state:=entry->>'default_state'; made.min_sandbox_level:=(entry->>'min_sandbox_level')::integer;
  made.manifest_sha256:=entry->>'manifest_sha256'; made.credential_locus:=coalesce(entry->>'credential_locus','server');
  made.declared_permissions:=coalesce(ARRAY(SELECT jsonb_array_elements_text(entry->'declared_permissions')),'{}');
  made.granted_permissions:=coalesce(ARRAY(SELECT jsonb_array_elements_text(entry->'granted_permissions')),'{}');
  made.attributes:=coalesce(entry->'attributes','{}'::jsonb);
  IF expected=0 THEN
   INSERT INTO forge.capability_catalog(id,kind,version,risk,is_base,default_state,min_sandbox_level,manifest_sha256,
    credential_locus,declared_permissions,granted_permissions,attributes)
   VALUES(made.id,made.kind,made.version,made.risk,made.is_base,made.default_state,made.min_sandbox_level,made.manifest_sha256,
    made.credential_locus,made.declared_permissions,made.granted_permissions,made.attributes);
   PERFORM forge.cap_audit('platform',NULL,actor,'catalog.created',cid,NULL,'r1');
   PERFORM forge.cap_bump_platform();
  ELSIF (cur.version,cur.risk,cur.is_base,cur.default_state,cur.min_sandbox_level,cur.manifest_sha256,cur.credential_locus,
    cur.declared_permissions,cur.granted_permissions,cur.attributes) IS DISTINCT FROM
   (made.version,made.risk,made.is_base,made.default_state,made.min_sandbox_level,made.manifest_sha256,made.credential_locus,
    made.declared_permissions,made.granted_permissions,made.attributes) THEN
   UPDATE forge.capability_catalog c SET version=made.version,risk=made.risk,is_base=made.is_base,default_state=made.default_state,
    min_sandbox_level=made.min_sandbox_level,manifest_sha256=made.manifest_sha256,credential_locus=made.credential_locus,
    declared_permissions=made.declared_permissions,granted_permissions=made.granted_permissions,attributes=made.attributes,
    revision=c.revision+1,updated_at=clock_timestamp() WHERE c.id=cid;
   PERFORM forge.cap_audit('platform',NULL,actor,'catalog.updated',cid,'r'||cur.revision,'r'||(cur.revision+1));
   PERFORM forge.cap_bump_platform();
  END IF;
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END;
 RETURN QUERY SELECT c.id,c.kind,c.version,c.risk,c.is_base,c.default_state,c.min_sandbox_level,c.manifest_sha256,
  c.credential_locus,c.declared_permissions,c.granted_permissions,c.revision FROM forge.capability_catalog c WHERE c.id=cid;
END $$;

CREATE FUNCTION forge.cap_catalog_list(digest text)
RETURNS TABLE(id text,kind text,version text,risk text,is_base boolean,default_state text,min_sandbox_level integer,
 manifest_sha256 text,credential_locus text,declared_permissions text[],granted_permissions text[],revision bigint,
 platform_state text,platform_lock text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 RETURN QUERY SELECT c.id,c.kind,c.version,c.risk,c.is_base,c.default_state,c.min_sandbox_level,c.manifest_sha256,
  c.credential_locus,c.declared_permissions,c.granted_permissions,c.revision,p.state,coalesce(p.lock,'none')
  FROM forge.capability_catalog c LEFT JOIN forge.capability_platform_policy p ON p.capability_id=c.id ORDER BY c.id;
END $$;

CREATE FUNCTION forge.cap_platform_policy_set(digest text,cid text,new_state text,new_lock text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; cur forge.capability_platform_policy%ROWTYPE; had boolean;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF cid IS NULL OR new_lock IS NULL OR new_lock NOT IN ('none','forced_off') OR (new_state IS NOT NULL AND new_state NOT IN ('on','off')) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END IF;
 PERFORM 1 FROM forge.capability_catalog c WHERE c.id=cid;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_NOT_FOUND'; END IF;
 SELECT * INTO cur FROM forge.capability_platform_policy p WHERE p.capability_id=cid FOR UPDATE;
 had:=FOUND;
 IF had AND cur.state IS NOT DISTINCT FROM new_state AND cur.lock=new_lock THEN RETURN false; END IF;
 IF NOT had AND new_state IS NULL AND new_lock='none' THEN RETURN false; END IF;
 INSERT INTO forge.capability_platform_policy(capability_id,state,lock) VALUES(cid,new_state,new_lock)
 ON CONFLICT(capability_id) DO UPDATE SET state=excluded.state,lock=excluded.lock,updated_at=clock_timestamp();
 PERFORM forge.cap_audit('platform',NULL,actor,'platform.policy_set',cid,
  CASE WHEN had THEN forge.cap_word(cur.state,cur.lock) END,forge.cap_word(new_state,new_lock));
 PERFORM forge.cap_bump_platform();
 RETURN true;
END $$;

CREATE FUNCTION forge.cap_company_override_set(digest text,org uuid,cid text,new_state text,new_lock text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; cur forge.capability_company_overrides%ROWTYPE; had boolean;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF org IS NULL OR cid IS NULL OR new_lock IS NULL OR new_lock NOT IN ('none','forced_off')
  OR (new_state IS NOT NULL AND new_state NOT IN ('on','off')) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END IF;
 PERFORM set_config('forge.organization',org::text,true);
 PERFORM 1 FROM forge.capability_catalog c WHERE c.id=cid;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_NOT_FOUND'; END IF;
 SELECT * INTO cur FROM forge.capability_company_overrides o WHERE o.organization_id=org AND o.capability_id=cid FOR UPDATE;
 had:=FOUND;
 IF (had AND cur.state IS NOT DISTINCT FROM new_state AND cur.lock=new_lock) OR (NOT had AND new_state IS NULL AND new_lock='none') THEN
  RETURN false;
 END IF;
 -- The foreign key is the existence check for the company: the authority reads no organization row (nothing to leak either way).
 BEGIN
  INSERT INTO forge.capability_company_overrides(organization_id,capability_id,state,lock) VALUES(org,cid,new_state,new_lock)
  ON CONFLICT(organization_id,capability_id) DO UPDATE SET state=excluded.state,lock=excluded.lock,updated_at=clock_timestamp();
  PERFORM forge.cap_audit('org',org,actor,'company.policy_set',cid,
   CASE WHEN had THEN forge.cap_word(cur.state,cur.lock) END,forge.cap_word(new_state,new_lock));
  PERFORM forge.cap_bump_org(org);
 EXCEPTION WHEN foreign_key_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_NOT_FOUND';
 END;
 RETURN true;
END $$;

-- Layers read by a platform owner for one company: the override and the administrator setting side by side.
CREATE FUNCTION forge.cap_company_policy_get(digest text,org uuid)
RETURNS TABLE(capability_id text,company_state text,company_lock text,org_enabled boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 IF org IS NULL THEN RETURN; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 RETURN QUERY SELECT c.id,o.state,coalesce(o.lock,'none'),s.enabled FROM forge.capability_catalog c
  LEFT JOIN forge.capability_company_overrides o ON o.organization_id=org AND o.capability_id=c.id
  LEFT JOIN forge.capability_org_settings s ON s.organization_id=org AND s.capability_id=c.id
  WHERE o.capability_id IS NOT NULL OR s.capability_id IS NOT NULL ORDER BY c.id;
END $$;

-- The company administrator's one write: enable (true), disable (false) or return to inherited (NULL), never against a lock.
CREATE FUNCTION forge.cap_org_set(digest text,org uuid,cid text,want boolean) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; cur boolean; had boolean; locked boolean;
BEGIN
 actor:=forge.cap_lock_admin(digest,org);
 IF cid IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID'; END IF;
 PERFORM 1 FROM forge.capability_catalog c WHERE c.id=cid;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_NOT_FOUND'; END IF;
 SELECT EXISTS(SELECT 1 FROM forge.capability_platform_policy p WHERE p.capability_id=cid AND p.lock='forced_off')
  OR EXISTS(SELECT 1 FROM forge.capability_company_overrides o WHERE o.organization_id=org AND o.capability_id=cid AND o.lock='forced_off')
  INTO locked;
 IF locked THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_LOCKED'; END IF;
 SELECT s.enabled INTO cur FROM forge.capability_org_settings s WHERE s.organization_id=org AND s.capability_id=cid FOR UPDATE;
 had:=FOUND;
 IF (NOT had AND want IS NULL) OR (had AND cur IS NOT DISTINCT FROM want) THEN RETURN false; END IF;
 IF want IS NULL THEN
  DELETE FROM forge.capability_org_settings s WHERE s.organization_id=org AND s.capability_id=cid;
 ELSE
  INSERT INTO forge.capability_org_settings(organization_id,capability_id,enabled,updated_by) VALUES(org,cid,want,actor)
  ON CONFLICT(organization_id,capability_id) DO UPDATE SET enabled=excluded.enabled,updated_by=excluded.updated_by,updated_at=clock_timestamp();
 END IF;
 PERFORM forge.cap_audit('org',org,actor,CASE WHEN want IS NULL THEN 'org.setting_cleared' ELSE 'org.setting_set' END,cid,
  CASE WHEN had THEN CASE WHEN cur THEN 'on' ELSE 'off' END END,CASE WHEN want IS NULL THEN 'inherit' WHEN want THEN 'on' ELSE 'off' END);
 PERFORM forge.cap_bump_org(org);
 RETURN true;
END $$;

-- The layers, one row per catalog entry, for the resolver. A member reads them for the policy document; an administrator for
-- the company page. The attributes column of the catalog is never returned here.
CREATE FUNCTION forge.cap_layers(org uuid)
RETURNS TABLE(id text,kind text,version text,risk text,is_base boolean,default_state text,min_sandbox_level integer,
 manifest_sha256 text,credential_locus text,declared_permissions text[],granted_permissions text[],platform_state text,
 platform_lock text,company_state text,company_lock text,org_enabled boolean,platform_epoch bigint,org_epoch bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT c.id,c.kind,c.version,c.risk,c.is_base,c.default_state,c.min_sandbox_level,c.manifest_sha256,c.credential_locus,
  c.declared_permissions,c.granted_permissions,p.state,coalesce(p.lock,'none'),o.state,coalesce(o.lock,'none'),s.enabled,
  coalesce((SELECT e.epoch FROM forge.capability_platform_epoch e WHERE e.singleton),1),
  coalesce((SELECT g.epoch FROM forge.capability_org_epochs g WHERE g.organization_id=org),1)
 FROM forge.capability_catalog c
 LEFT JOIN forge.capability_platform_policy p ON p.capability_id=c.id
 LEFT JOIN forge.capability_company_overrides o ON o.organization_id=org AND o.capability_id=c.id
 LEFT JOIN forge.capability_org_settings s ON s.organization_id=org AND s.capability_id=c.id
 ORDER BY c.id
$$;

CREATE FUNCTION forge.cap_read_layers(digest text,org uuid)
RETURNS TABLE(id text,kind text,version text,risk text,is_base boolean,default_state text,min_sandbox_level integer,
 manifest_sha256 text,credential_locus text,declared_permissions text[],granted_permissions text[],platform_state text,
 platform_lock text,company_state text,company_lock text,org_enabled boolean,platform_epoch bigint,org_epoch bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.cap_lock_member(digest,org);
 PERFORM set_config('forge.organization',org::text,true);
 RETURN QUERY SELECT * FROM forge.cap_layers(org);
END $$;

CREATE FUNCTION forge.cap_admin_layers(digest text,org uuid)
RETURNS TABLE(id text,kind text,version text,risk text,is_base boolean,default_state text,min_sandbox_level integer,
 manifest_sha256 text,credential_locus text,declared_permissions text[],granted_permissions text[],platform_state text,
 platform_lock text,company_state text,company_lock text,org_enabled boolean,platform_epoch bigint,org_epoch bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.cap_lock_admin(digest,org);
 RETURN QUERY SELECT * FROM forge.cap_layers(org);
END $$;

-- Newest first; the company audit is the administrator's own company only, the platform audit is every row for an owner.
CREATE FUNCTION forge.cap_org_audit_page(digest text,org uuid,before_id bigint,page integer)
RETURNS TABLE(id bigint,scope text,actor_id uuid,action text,target text,before_state text,after_state text,at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.cap_lock_admin(digest,org);
 IF page IS NULL OR page NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID'; END IF;
 RETURN QUERY SELECT a.id,a.scope,a.actor_id,a.action,a.target,a.before_state,a.after_state,a.at FROM forge.capability_change_audit a
  WHERE a.organization_id=org AND (before_id IS NULL OR a.id<before_id) ORDER BY a.id DESC LIMIT page;
END $$;

CREATE FUNCTION forge.cap_platform_audit_page(digest text,before_id bigint,page integer)
RETURNS TABLE(id bigint,scope text,organization_id uuid,actor_id uuid,action text,target text,before_state text,after_state text,at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 IF page IS NULL OR page NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID'; END IF;
 PERFORM set_config('forge.cap_platform','1',true);
 RETURN QUERY SELECT a.id,a.scope,a.organization_id,a.actor_id,a.action,a.target,a.before_state,a.after_state,a.at
  FROM forge.capability_change_audit a WHERE before_id IS NULL OR a.id<before_id ORDER BY a.id DESC LIMIT page;
 PERFORM set_config('forge.cap_platform','',true);
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_capability_authority;
REVOKE ALL ON FUNCTION forge.cap_lock_admin(text,uuid),forge.cap_lock_member(text,uuid),
 forge.cap_audit(text,uuid,uuid,text,text,text,text),forge.cap_word(text,text),forge.cap_bump_platform(),forge.cap_bump_org(uuid),
 forge.cap_layers(uuid),forge.cap_catalog_put(text,text,bigint,jsonb),forge.cap_catalog_list(text),
 forge.cap_platform_policy_set(text,text,text,text),forge.cap_company_override_set(text,uuid,text,text,text),
 forge.cap_company_policy_get(text,uuid),forge.cap_org_set(text,uuid,text,boolean),forge.cap_read_layers(text,uuid),
 forge.cap_admin_layers(text,uuid),forge.cap_org_audit_page(text,uuid,bigint,integer),
 forge.cap_platform_audit_page(text,bigint,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.cap_catalog_put(text,text,bigint,jsonb),forge.cap_catalog_list(text),
 forge.cap_platform_policy_set(text,text,text,text),forge.cap_company_override_set(text,uuid,text,text,text),
 forge.cap_company_policy_get(text,uuid),forge.cap_org_set(text,uuid,text,boolean),forge.cap_read_layers(text,uuid),
 forge.cap_admin_layers(text,uuid),forge.cap_org_audit_page(text,uuid,bigint,integer),
 forge.cap_platform_audit_page(text,bigint,integer) TO forge_capability_service;
COMMIT;
