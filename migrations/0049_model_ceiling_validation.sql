-- The model ceiling is chosen from discovered models, never typed. Additive and forward-only (functions only).
-- * forge.platform_company_model_access_set (0032) now refuses a ceiling that names a model the company's keys have not
--   been discovered to reach: PLATFORM_INVALID while the company has no current discovery (matching its profile
--   revision and binding), MODEL_NOT_DISCOVERED when any entry is missing from that discovery. The empty list stays valid
--   (it denies everything, so it needs no discovery). Every other check and the audit row are unchanged.
-- * forge.gateway_catalog_publish (0033) refuses an alias outside the ceiling with GATEWAY_OUTSIDE_CEILING instead of the
--   generic GATEWAY_DENIED, so the administrator can be told the ceiling is the reason. Nothing else in it changes.
-- * Two read helpers owned by the gateway authority, because only it may read the discovery table: the current discovery
--   of a company for the platform authority, and the ceiling of a company for the administrator's catalogue refresh, which
--   lists only the models the administrator can publish.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';

GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;

-- The discovery that matches the company's current profile revision and binding; NULL when there is none.
CREATE FUNCTION forge.gateway_discovered_models(org uuid) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE found jsonb;
BEGIN
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 SELECT d.model_ids INTO found FROM forge.organization_gateway_profiles p
 JOIN forge.gateway_model_discoveries d ON d.organization_id=p.organization_id
  AND d.binding_id=p.binding_id AND d.gateway_revision=p.revision
 WHERE p.organization_id=org;
 RETURN found;
END $$;

-- The platform ceiling of the administrator's company (NULL = unrestricted or no profile).
CREATE FUNCTION forge.gateway_catalog_ceiling(digest text,org uuid) RETURNS text[]
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE found text[];
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 SELECT p.ceiling INTO found FROM forge.organization_gateway_profiles p WHERE p.organization_id=org;
 RETURN found;
END $$;

-- Body of 0033 with one change: the ceiling refusal carries its own message.
CREATE OR REPLACE FUNCTION forge.gateway_catalog_publish(digest text,org uuid,operation uuid,expected bigint,
 gateway_revision bigint,binding uuid,mapping jsonb,default_alias text,payload text,checksum text,selection_hash text)
RETURNS bigint LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; member uuid; g record; d record; prior record; current_revision bigint; event uuid;
BEGIN
 account:=forge.gateway_lock_admin(digest,org);
 member:=forge.gateway_resolve_member(org,account);
 IF member IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED'; END IF;
 SELECT * INTO g FROM forge.organization_gateway_profiles WHERE organization_id=org;
 IF NOT FOUND OR g.revision IS DISTINCT FROM gateway_revision OR g.binding_id IS DISTINCT FROM binding THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
 END IF;
 SELECT * INTO d FROM forge.gateway_model_discoveries WHERE organization_id=org FOR UPDATE;
 IF NOT FOUND OR d.gateway_revision<>g.revision OR d.binding_id<>g.binding_id THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
 END IF;
 IF operation IS NULL OR expected IS NULL OR expected NOT BETWEEN 0 AND 9223372036854775805
 OR mapping IS NULL OR jsonb_typeof(mapping)<>'object' OR default_alias IS NULL
 OR NOT mapping ? default_alias OR (SELECT count(*) FROM jsonb_each(mapping)) NOT BETWEEN 1 AND 64
 OR EXISTS(SELECT 1 FROM jsonb_each(mapping) e WHERE e.key !~ '^[a-z][a-z0-9_-]{0,63}$'
   OR jsonb_typeof(e.value)<>'string' OR NOT d.model_ids @> jsonb_build_array(e.value)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 -- The platform ceiling: an alias outside it is refused and nothing is written (replay of an old operation is checked below).
 IF g.ceiling IS NOT NULL AND EXISTS(SELECT 1 FROM jsonb_each(mapping) e WHERE NOT (e.value#>>'{}')=ANY(g.ceiling)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_OUTSIDE_CEILING';
 END IF;
 -- Recompute selection identity here so trusted store callers cannot hide mapping drift.
 IF selection_hash IS DISTINCT FROM encode(sha256(convert_to(
   '{"default":'||to_json(default_alias)::text||',"gateway_revision":'||gateway_revision::text
   ||',"mapping":{'||(SELECT string_agg(to_json(key)::text||':'||to_json(value#>>'{}')::text,',' ORDER BY key)
   FROM jsonb_each(mapping))||'}}','UTF8')),'hex') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 SELECT * INTO prior FROM forge.catalog_publication_operations WHERE operation_id=operation;
 IF FOUND THEN
  IF prior.organization_id<>org OR prior.actor_id<>member OR prior.router_binding_id<>binding
   OR prior.expected_revision<>expected OR prior.payload_sha256<>checksum
   OR prior.gateway_revision IS DISTINCT FROM gateway_revision OR prior.selection_sha256 IS DISTINCT FROM selection_hash THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
  END IF;
  RETURN prior.catalog_revision;
 END IF;
 SELECT p.catalog_revision INTO current_revision FROM forge.active_model_catalogs p WHERE p.organization_id=org FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
 END IF;
 -- The immutable codec payload must match the selected public aliases exactly.
 IF payload IS NULL OR length(payload)>1048576 OR payload::jsonb->>'schema_version'<>'2'
 OR payload::jsonb->>'organization_id'<>org::text OR payload::jsonb->>'router_binding_id'<>binding::text
 OR (payload::jsonb->>'revision')::bigint<>expected+1
 OR (SELECT array_agg(a->>'name' ORDER BY a->>'name') FROM jsonb_array_elements(payload::jsonb->'aliases') a)
 IS DISTINCT FROM (SELECT array_agg(key ORDER BY key) FROM jsonb_each(mapping)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(payload::jsonb->'aliases') a
  WHERE jsonb_typeof(a->'routes')<>'array' OR jsonb_array_length(a->'routes')<>1
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(a->'routes') r
   WHERE r->>'organization_id' IS DISTINCT FROM org::text
    OR r->>'router_binding_id' IS DISTINCT FROM binding::text
    OR r->>'verification' IS DISTINCT FROM 'unverified'
    OR r->'capabilities' IS DISTINCT FROM
     '{"capability_state":"unknown","verification":"unverified","input_modalities":null,"output_modalities":null,"tools":null,"streaming":null,"max_context_tokens":null,"max_output_tokens":null}'::jsonb)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 event:=gen_random_uuid();
 INSERT INTO forge.model_catalog_snapshots(organization_id,router_binding_id,revision,payload,payload_sha256)
 VALUES(org,binding,expected+1,payload,checksum);
 INSERT INTO forge.gateway_catalog_selections VALUES(org,binding,expected+1,gateway_revision,default_alias,mapping,selection_hash);
 INSERT INTO forge.outbox_events(event_id,organization_id,actor_id,request_id,resource_id,event_type,previous_revision,revision,schema_version,outcome)
 VALUES(event,org,member,operation,binding,'model_catalog.published',expected,expected+1,1,'succeeded');
 INSERT INTO forge.active_model_catalogs(organization_id,router_binding_id,catalog_revision,event_id)
 VALUES(org,binding,expected+1,event) ON CONFLICT(organization_id) DO UPDATE
 SET router_binding_id=excluded.router_binding_id,catalog_revision=excluded.catalog_revision,event_id=excluded.event_id;
 INSERT INTO forge.catalog_publication_operations(operation_id,organization_id,actor_id,router_binding_id,expected_revision,
  catalog_revision,payload_sha256,event_id,gateway_revision,selection_sha256)
 VALUES(operation,org,member,binding,expected,expected+1,checksum,event,gateway_revision,selection_hash);
 RETURN expected+1;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.gateway_discovered_models(uuid),forge.gateway_catalog_ceiling(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.gateway_discovered_models(uuid) TO forge_platform_authority;
GRANT EXECUTE ON FUNCTION forge.gateway_catalog_ceiling(text,uuid) TO forge_gateway_service;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- 0032 plus the discovery check: a ceiling is a subset of what the company's keys were discovered to reach.
CREATE OR REPLACE FUNCTION forge.platform_company_model_access_set(digest text,org uuid,models text[]) RETURNS text[]
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; discovered jsonb;
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
 IF cardinality(models)>0 THEN
  discovered:=forge.gateway_discovered_models(org);
  IF discovered IS NULL THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
  END IF;
  IF EXISTS(SELECT 1 FROM unnest(models) m WHERE NOT discovered ? m) THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MODEL_NOT_DISCOVERED';
  END IF;
 END IF;
 INSERT INTO forge.organization_gateway_profiles(organization_id,revision,binding_id,ceiling)
 VALUES(org,1,gen_random_uuid(),models)
 ON CONFLICT(organization_id) DO UPDATE SET ceiling=excluded.ceiling,updated_at=clock_timestamp();
 PERFORM forge.platform_audit_write(actor,'company.model_access_set',org,NULL);
 RETURN models;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
COMMIT;
