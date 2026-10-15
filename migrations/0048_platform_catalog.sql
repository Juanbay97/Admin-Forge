-- Platform model discovery and catalog publication. Additive and forward-only.
-- A fresh verified platform owner can, for one company: open the company's assigned gateway keys to discover the models they
-- can reach (the union is stored as the company's discovery, exactly what the administrator's refresh stores), read the
-- discovery with the published selection, and publish the catalog (aliases, default) on the company's profile binding. Publishing
-- also sets the platform model ceiling to the selected upstream models in the same transaction, so what the owner selects is
-- exactly what the company may use.
-- * The catalog tables stay writable only by the gateway authority: the four functions below are owned by it, like the
--   administrator's, and each starts by asking a platform-authority helper to authorize a fresh verified owner and pin the
--   company. No table grant changes; the gateway authority gains EXECUTE on two internal helpers only.
-- * The published event names a real membership of the company (an administrator when there is one, else any active member):
--   the publication log references memberships. The platform audit row carries the real actor (the owner).
-- * The platform audit action list gains the two actions written here.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

ALTER TABLE forge.platform_audit_log DROP CONSTRAINT platform_audit_log_action_check;
ALTER TABLE forge.platform_audit_log ADD CONSTRAINT platform_audit_log_action_check CHECK(action IN
 ('company.created','company.suspended','company.reactivated','company.branding_saved','owner.mfa_enrolled',
  'owner.mfa_recovery_used','gateway_key.created','gateway_key.rotated','gateway_key.status_changed',
  'company.gateway_assigned','company.model_access_set','model_price.set',
  'company.models_discovered','company.catalog_published'));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- Internal: a fresh verified owner, the company pinned for row security, and who the publication event may name.
CREATE FUNCTION forge.platform_catalog_authorize(digest text,org uuid,fresh boolean)
RETURNS TABLE(owner_id uuid,member_id uuid,org_active boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; member uuid; enabled boolean;
BEGIN
 actor:=forge.platform_lock_owner(digest,fresh);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 SELECT o.active INTO enabled FROM forge.organizations o WHERE o.id=org;
 IF org IS NULL OR NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 SELECT m.id INTO member FROM forge.memberships m WHERE m.organization_id=org AND m.status='active'
  ORDER BY EXISTS(SELECT 1 FROM forge.membership_roles r WHERE r.organization_id=m.organization_id
   AND r.membership_id=m.id AND r.role='organization_admin') DESC,m.id LIMIT 1;
 RETURN QUERY SELECT actor,member,enabled;
END $$;

-- Internal: the audit row of a catalog action and, for a publication, the new platform ceiling (written by the authority
-- that owns the profile). Callers pass the owner the authorize helper returned; the owner role is checked again here.
CREATE FUNCTION forge.platform_catalog_record(owner uuid,org uuid,act text,new_ceiling text[]) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM 1 FROM forge.platform_roles r WHERE r.account_id=owner AND r.role='platform_owner';
 IF NOT FOUND OR act NOT IN ('company.models_discovered','company.catalog_published') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 IF new_ceiling IS NOT NULL THEN
  IF cardinality(new_ceiling)>500 OR coalesce(array_ndims(new_ceiling),1)<>1
   OR EXISTS(SELECT 1 FROM unnest(new_ceiling) m WHERE m IS NULL OR m !~ '^[!-~]{1,255}$')
   OR (SELECT count(DISTINCT m) FROM unnest(new_ceiling) m)<>cardinality(new_ceiling) THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
  END IF;
  UPDATE forge.organization_gateway_profiles SET ceiling=new_ceiling,updated_at=clock_timestamp() WHERE organization_id=org;
 END IF;
 PERFORM forge.platform_audit_write(owner,act,org,NULL);
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_catalog_authorize(text,uuid,boolean),forge.platform_catalog_record(uuid,uuid,text,text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_catalog_authorize(text,uuid,boolean),forge.platform_catalog_record(uuid,uuid,text,text[])
 TO forge_gateway_authority;

GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;

-- The company's assigned keys, lowest priority first, with the sealed value the application opens to ask each key for its
-- models. A company without any assignment has no profile and no rows. The audit row is written when the keys are read.
CREATE FUNCTION forge.platform_catalog_keys(digest text,org uuid)
RETURNS TABLE(revision bigint,binding_id uuid,key_id uuid,label text,origin text,priority integer,assigned_active boolean,
 key_status text,key_revision bigint,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record;
BEGIN
 SELECT * INTO a FROM forge.platform_catalog_authorize(digest,org,true);
 PERFORM forge.platform_catalog_record(a.owner_id,org,'company.models_discovered',NULL);
 RETURN QUERY SELECT p.revision,p.binding_id,k.id,k.label,k.origin,x.priority,x.active,k.status,k.revision,k.encrypted_key
  FROM forge.organization_gateway_profiles p
  JOIN forge.organization_gateway_keys x ON x.organization_id=p.organization_id
  JOIN forge.gateway_keys k ON k.id=x.key_id
  WHERE p.organization_id=org ORDER BY x.priority;
END $$;

-- Same contract as gateway_catalog_refresh (0033), authorized as the platform owner.
CREATE FUNCTION forge.platform_catalog_discovery_save(digest text,org uuid,expected bigint,binding uuid,ids jsonb)
RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record; g record; stamp timestamptz;
BEGIN
 SELECT * INTO a FROM forge.platform_catalog_authorize(digest,org,true);
 IF NOT a.org_active THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID'; END IF;
 SELECT * INTO g FROM forge.organization_gateway_profiles WHERE organization_id=org;
 IF NOT FOUND OR g.revision IS DISTINCT FROM expected OR g.binding_id IS DISTINCT FROM binding THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT';
 END IF;
 IF ids IS NULL OR jsonb_typeof(ids)<>'array' OR jsonb_array_length(ids) NOT BETWEEN 1 AND 500
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(ids) e WHERE jsonb_typeof(e)<>'string' OR (e#>>'{}') !~ '^[!-~]{1,255}$')
  OR (SELECT count(DISTINCT value) FROM jsonb_array_elements(ids))<>jsonb_array_length(ids) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 INSERT INTO forge.gateway_model_discoveries(organization_id,gateway_revision,binding_id,model_ids)
 VALUES(org,expected,binding,ids) ON CONFLICT(organization_id) DO UPDATE
 SET gateway_revision=excluded.gateway_revision,binding_id=excluded.binding_id,
 model_ids=excluded.model_ids,recorded_at=clock_timestamp() RETURNING recorded_at INTO stamp;
 RETURN stamp;
END $$;

-- One row: the profile binding, the platform ceiling, the current discovery (when it matches the profile), and the published
-- selection with its alias mapping. No row when the company has no assignment (no profile).
CREATE FUNCTION forge.platform_catalog_status(digest text,org uuid)
RETURNS TABLE(revision bigint,binding_id uuid,ceiling text[],discovered jsonb,discovered_at timestamptz,
 catalogue_revision bigint,default_alias text,publication_state text,mapping jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record; prof record; pointer record; selected record;
 found_ids jsonb; found_at timestamptz;
BEGIN
 SELECT * INTO a FROM forge.platform_catalog_authorize(digest,org,false);
 SELECT p.* INTO prof FROM forge.organization_gateway_profiles p WHERE p.organization_id=org;
 IF NOT FOUND THEN RETURN; END IF;
 SELECT d.model_ids,d.recorded_at INTO found_ids,found_at FROM forge.gateway_model_discoveries d
  WHERE d.organization_id=org AND d.binding_id=prof.binding_id AND d.gateway_revision=prof.revision;
 SELECT p.* INTO pointer FROM forge.active_model_catalogs p WHERE p.organization_id=org;
 IF NOT FOUND THEN
  RETURN QUERY SELECT prof.revision,prof.binding_id,prof.ceiling,found_ids,found_at,0::bigint,NULL::text,'UNPUBLISHED'::text,NULL::jsonb;
  RETURN;
 END IF;
 SELECT m.* INTO selected FROM forge.gateway_catalog_selections m
  WHERE m.organization_id=org AND m.binding_id=pointer.router_binding_id AND m.catalog_revision=pointer.catalog_revision;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_UNAVAILABLE'; END IF;
 RETURN QUERY SELECT prof.revision,prof.binding_id,prof.ceiling,found_ids,found_at,pointer.catalog_revision,selected.default_alias,
  CASE WHEN prof.binding_id=pointer.router_binding_id AND prof.revision=selected.gateway_revision
   THEN 'CURRENT' ELSE 'STALE_GATEWAY' END,selected.private_mapping;
END $$;

-- Same contract as gateway_catalog_publish (0033), authorized as the platform owner. The ceiling becomes exactly the set of
-- upstream models selected, in this same transaction (a failure leaves both untouched).
CREATE FUNCTION forge.platform_catalog_publish(digest text,org uuid,operation uuid,expected bigint,
 gateway_revision bigint,binding uuid,mapping jsonb,default_alias text,payload text,checksum text,selection_hash text)
RETURNS bigint LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record; g record; d record; prior record; current_revision bigint; event uuid; chosen text[];
BEGIN
 SELECT * INTO a FROM forge.platform_catalog_authorize(digest,org,true);
 IF NOT a.org_active THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID'; END IF;
 IF a.member_id IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CATALOG_NO_MEMBER'; END IF;
 SELECT * INTO g FROM forge.organization_gateway_profiles WHERE organization_id=org;
 IF NOT FOUND OR g.revision IS DISTINCT FROM gateway_revision OR g.binding_id IS DISTINCT FROM binding THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT';
 END IF;
 SELECT * INTO d FROM forge.gateway_model_discoveries WHERE organization_id=org FOR UPDATE;
 IF NOT FOUND OR d.gateway_revision<>g.revision OR d.binding_id<>g.binding_id THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT';
 END IF;
 IF operation IS NULL OR expected IS NULL OR expected NOT BETWEEN 0 AND 9223372036854775805
 OR mapping IS NULL OR jsonb_typeof(mapping)<>'object' OR default_alias IS NULL
 OR NOT mapping ? default_alias OR (SELECT count(*) FROM jsonb_each(mapping)) NOT BETWEEN 1 AND 64
 OR EXISTS(SELECT 1 FROM jsonb_each(mapping) e WHERE e.key !~ '^[a-z][a-z0-9_-]{0,63}$'
   OR jsonb_typeof(e.value)<>'string' OR NOT d.model_ids @> jsonb_build_array(e.value)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 IF selection_hash IS DISTINCT FROM encode(sha256(convert_to(
   '{"default":'||to_json(default_alias)::text||',"gateway_revision":'||gateway_revision::text
   ||',"mapping":{'||(SELECT string_agg(to_json(key)::text||':'||to_json(value#>>'{}')::text,',' ORDER BY key)
   FROM jsonb_each(mapping))||'}}','UTF8')),'hex') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 SELECT * INTO prior FROM forge.catalog_publication_operations WHERE operation_id=operation;
 IF FOUND THEN
  IF prior.organization_id<>org OR prior.router_binding_id<>binding
   OR prior.expected_revision<>expected OR prior.payload_sha256<>checksum
   OR prior.gateway_revision IS DISTINCT FROM gateway_revision OR prior.selection_sha256 IS DISTINCT FROM selection_hash THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT';
  END IF;
  RETURN prior.catalog_revision;
 END IF;
 SELECT p.catalog_revision INTO current_revision FROM forge.active_model_catalogs p WHERE p.organization_id=org FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT';
 END IF;
 IF payload IS NULL OR length(payload)>1048576 OR payload::jsonb->>'schema_version'<>'2'
 OR payload::jsonb->>'organization_id'<>org::text OR payload::jsonb->>'router_binding_id'<>binding::text
 OR (payload::jsonb->>'revision')::bigint<>expected+1
 OR (SELECT array_agg(a2->>'name' ORDER BY a2->>'name') FROM jsonb_array_elements(payload::jsonb->'aliases') a2)
 IS DISTINCT FROM (SELECT array_agg(key ORDER BY key) FROM jsonb_each(mapping)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(payload::jsonb->'aliases') a2
  WHERE jsonb_typeof(a2->'routes')<>'array' OR jsonb_array_length(a2->'routes')<>1
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(a2->'routes') r
   WHERE r->>'organization_id' IS DISTINCT FROM org::text
    OR r->>'router_binding_id' IS DISTINCT FROM binding::text
    OR r->>'verification' IS DISTINCT FROM 'unverified'
    OR r->'capabilities' IS DISTINCT FROM
     '{"capability_state":"unknown","verification":"unverified","input_modalities":null,"output_modalities":null,"tools":null,"streaming":null,"max_context_tokens":null,"max_output_tokens":null}'::jsonb)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 SELECT array_agg(DISTINCT e.value#>>'{}' ORDER BY e.value#>>'{}') INTO chosen FROM jsonb_each(mapping) e;
 PERFORM forge.platform_catalog_record(a.owner_id,org,'company.catalog_published',chosen);
 event:=gen_random_uuid();
 INSERT INTO forge.model_catalog_snapshots(organization_id,router_binding_id,revision,payload,payload_sha256)
 VALUES(org,binding,expected+1,payload,checksum);
 INSERT INTO forge.gateway_catalog_selections VALUES(org,binding,expected+1,gateway_revision,default_alias,mapping,selection_hash);
 INSERT INTO forge.outbox_events(event_id,organization_id,actor_id,request_id,resource_id,event_type,previous_revision,revision,schema_version,outcome)
 VALUES(event,org,a.member_id,operation,binding,'model_catalog.published',expected,expected+1,1,'succeeded');
 INSERT INTO forge.active_model_catalogs(organization_id,router_binding_id,catalog_revision,event_id)
 VALUES(org,binding,expected+1,event) ON CONFLICT(organization_id) DO UPDATE
 SET router_binding_id=excluded.router_binding_id,catalog_revision=excluded.catalog_revision,event_id=excluded.event_id;
 INSERT INTO forge.catalog_publication_operations(operation_id,organization_id,actor_id,router_binding_id,expected_revision,
  catalog_revision,payload_sha256,event_id,gateway_revision,selection_sha256)
 VALUES(operation,org,a.member_id,binding,expected,expected+1,checksum,event,gateway_revision,selection_hash);
 RETURN expected+1;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.platform_catalog_keys(text,uuid),forge.platform_catalog_discovery_save(text,uuid,bigint,uuid,jsonb),
 forge.platform_catalog_status(text,uuid),
 forge.platform_catalog_publish(text,uuid,uuid,bigint,bigint,uuid,jsonb,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_catalog_keys(text,uuid),forge.platform_catalog_discovery_save(text,uuid,bigint,uuid,jsonb),
 forge.platform_catalog_status(text,uuid),
 forge.platform_catalog_publish(text,uuid,uuid,bigint,bigint,uuid,jsonb,text,text,text,text) TO forge_platform_service;
COMMIT;
