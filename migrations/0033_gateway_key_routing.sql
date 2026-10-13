-- Gateway key routing and catalog rebinding. Additive in behaviour, forward-only.
-- * The catalog binding moves from the single per-company key row (organization_gateways) to the company profile
--   (organization_gateway_profiles: binding_id + revision, stable across key rotation, reorder and failover). The
--   backfill below copies every legacy row's binding_id and revision, so existing snapshots, selections and
--   discoveries keep matching and a published catalog stays CURRENT across the upgrade. A backfilled profile has no
--   ceiling (NULL = unrestricted): the platform narrows it explicitly.
-- * Routing reads the company's active assigned keys in priority order (rows, one per candidate) and falls back to the
--   legacy sealed key only while the company has no assignment at all (a platform that assigns and disables keys
--   is never bypassed by an old key); a model outside the platform-set ceiling is denied
--   on the next request, which is how a shrink applies immediately.
-- * Publishing refuses any alias whose upstream model is outside the ceiling.
-- The legacy gateway_inference_route stays untouched (unused by the application now); legacy rows are never modified.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;

-- The key the administrator's catalogue refresh and publish verify against: the lowest-priority active usable pool
-- key, else the legacy row that still carries the profile's binding. Nothing is returned without a usable key.
CREATE FUNCTION forge.gateway_catalog_key(digest text,org uuid)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text,key_id uuid,key_revision bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 RETURN QUERY SELECT p.revision,p.binding_id,k.origin,k.encrypted_key,k.id,k.revision
  FROM forge.organization_gateway_profiles p
  JOIN forge.organization_gateway_keys a ON a.organization_id=p.organization_id AND a.active
  JOIN forge.gateway_keys k ON k.id=a.key_id AND k.status='active' AND k.encrypted_key IS NOT NULL
  WHERE p.organization_id=org ORDER BY a.priority LIMIT 1;
 IF NOT FOUND AND NOT EXISTS(SELECT 1 FROM forge.organization_gateway_keys a WHERE a.organization_id=org) THEN
  RETURN QUERY SELECT p.revision,p.binding_id,g.endpoint,g.encrypted_key,NULL::uuid,NULL::bigint
   FROM forge.organization_gateway_profiles p
   JOIN forge.organization_gateways g ON g.organization_id=p.organization_id AND g.binding_id=p.binding_id
   WHERE p.organization_id=org;
 END IF;
END $$;

-- The administrator's whole view of the company gateway: configured or not, and how many keys are usable. Never a key,
-- an origin or a label.
CREATE FUNCTION forge.gateway_status(digest text,org uuid)
RETURNS TABLE(configured boolean,active_keys bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE usable bigint; legacy boolean;
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 SELECT count(*) INTO usable FROM forge.organization_gateway_keys a
  JOIN forge.gateway_keys k ON k.id=a.key_id AND k.status='active' AND k.encrypted_key IS NOT NULL
  WHERE a.organization_id=org AND a.active;
 SELECT EXISTS(SELECT 1 FROM forge.organization_gateway_profiles p
  JOIN forge.organization_gateways g ON g.organization_id=p.organization_id AND g.binding_id=p.binding_id
  WHERE p.organization_id=org) INTO legacy;
 IF usable=0 AND legacy AND NOT EXISTS(SELECT 1 FROM forge.organization_gateway_keys a WHERE a.organization_id=org) THEN
  usable:=1;
 END IF;
 RETURN QUERY SELECT usable>0,usable;
END $$;

-- Every candidate key of one alias, lowest priority first (the application tries each at most once).
CREATE FUNCTION forge.gateway_inference_candidates(digest text,org uuid,alias text)
RETURNS TABLE(catalog_revision bigint,upstream_id text,gateway_revision bigint,binding_id uuid,endpoint text,
 encrypted_key text,key_id uuid,key_revision bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; prof record; chosen record;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR forge.gateway_resolve_member(org,account) IS NULL
  OR alias IS NULL OR alias !~ '^[a-z][a-z0-9_-]{0,63}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 -- The member helper locked the organization, the account and the member and set the organization context.
 SELECT p.revision,p.binding_id,p.ceiling INTO prof FROM forge.organization_gateway_profiles p WHERE p.organization_id=org;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED'; END IF;
 SELECT a.catalog_revision AS revision,m.private_mapping->>alias AS upstream INTO chosen
  FROM forge.active_model_catalogs a
  JOIN forge.gateway_catalog_selections m ON m.organization_id=a.organization_id AND m.binding_id=a.router_binding_id
   AND m.catalog_revision=a.catalog_revision AND m.gateway_revision=prof.revision
  JOIN forge.model_catalog_snapshots s ON s.organization_id=a.organization_id AND s.router_binding_id=a.router_binding_id
   AND s.revision=a.catalog_revision
  WHERE a.organization_id=org AND a.router_binding_id=prof.binding_id AND m.private_mapping ? alias
   AND (m.private_mapping->>alias) ~ '^[!-~]{1,255}$';
 IF NOT FOUND OR (prof.ceiling IS NOT NULL AND NOT chosen.upstream=ANY(prof.ceiling)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 RETURN QUERY SELECT chosen.revision,chosen.upstream,prof.revision,prof.binding_id,k.origin,k.encrypted_key,k.id,k.revision
  FROM forge.organization_gateway_keys a
  JOIN forge.gateway_keys k ON k.id=a.key_id AND k.status='active' AND k.encrypted_key IS NOT NULL
  WHERE a.organization_id=org AND a.active ORDER BY a.priority;
 IF NOT FOUND AND NOT EXISTS(SELECT 1 FROM forge.organization_gateway_keys a WHERE a.organization_id=org) THEN
  RETURN QUERY SELECT chosen.revision,chosen.upstream,prof.revision,prof.binding_id,g.endpoint,g.encrypted_key,NULL::uuid,NULL::bigint
   FROM forge.organization_gateways g WHERE g.organization_id=org AND g.binding_id=prof.binding_id;
 END IF;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED'; END IF;
END $$;

-- Same contract as 0016 against the profile binding (no row lock needed: the profile binding never changes).
CREATE OR REPLACE FUNCTION forge.gateway_catalog_refresh(digest text,org uuid,expected bigint,binding uuid,ids jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g record;
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 SELECT * INTO g FROM forge.organization_gateway_profiles WHERE organization_id=org;
 IF NOT FOUND OR g.revision IS DISTINCT FROM expected OR g.binding_id IS DISTINCT FROM binding THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
 END IF;
 IF ids IS NULL OR jsonb_typeof(ids)<>'array' OR jsonb_array_length(ids) NOT BETWEEN 1 AND 500 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(ids) e WHERE jsonb_typeof(e)<>'string'
   OR (e#>>'{}') !~ '^[!-~]{1,255}$')
 OR (SELECT count(DISTINCT value) FROM jsonb_array_elements(ids))<>jsonb_array_length(ids) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 INSERT INTO forge.gateway_model_discoveries(organization_id,gateway_revision,binding_id,model_ids)
 VALUES(org,expected,binding,ids) ON CONFLICT(organization_id) DO UPDATE
 SET gateway_revision=excluded.gateway_revision,binding_id=excluded.binding_id,
 model_ids=excluded.model_ids,recorded_at=clock_timestamp();
END $$;

-- The return type gains the key identity, so the 0016 function is replaced rather than altered.
DROP FUNCTION forge.gateway_catalog_discovery(text,uuid);
CREATE FUNCTION forge.gateway_catalog_discovery(digest text,org uuid)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text,key_id uuid,key_revision bigint,model_ids jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 -- Set the organization context first: the discoveries policy is evaluated when the table is scanned, which a join
 -- may do before the key function would have set it.
 PERFORM forge.gateway_lock_admin(digest,org);
 RETURN QUERY SELECT k.revision,k.binding_id,k.endpoint,k.encrypted_key,k.key_id,k.key_revision,d.model_ids
 FROM forge.gateway_catalog_key(digest,org) k JOIN forge.gateway_model_discoveries d
 ON d.organization_id=org AND d.binding_id=k.binding_id AND d.gateway_revision=k.revision;
END $$;

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
 -- The platform ceiling: an alias outside it is denied and nothing is written (replay of an old operation is checked below).
 IF g.ceiling IS NOT NULL AND EXISTS(SELECT 1 FROM jsonb_each(mapping) e WHERE NOT (e.value#>>'{}')=ANY(g.ceiling)) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
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

CREATE OR REPLACE FUNCTION forge.gateway_catalog_member(digest text,org uuid)
RETURNS TABLE(payload text,payload_sha256 text,default_alias text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR forge.gateway_resolve_member(org,account) IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 RETURN QUERY SELECT s.payload,s.payload_sha256,m.default_alias FROM forge.active_model_catalogs p
 JOIN forge.organization_gateway_profiles g ON g.organization_id=p.organization_id AND g.binding_id=p.router_binding_id
 JOIN forge.gateway_catalog_selections m ON m.organization_id=p.organization_id AND m.binding_id=p.router_binding_id
  AND m.catalog_revision=p.catalog_revision AND m.gateway_revision=g.revision
 JOIN forge.model_catalog_snapshots s ON s.organization_id=p.organization_id AND s.router_binding_id=p.router_binding_id
  AND s.revision=p.catalog_revision WHERE p.organization_id=org;
END $$;

CREATE OR REPLACE FUNCTION forge.gateway_catalog_admin_status(digest text,org uuid)
RETURNS TABLE(catalogue_revision bigint,default_model text,publication_state text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE pointer record; selected record; gateway record;
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 SELECT g.* INTO gateway FROM forge.organization_gateway_profiles g WHERE g.organization_id=org;
 SELECT p.* INTO pointer FROM forge.active_model_catalogs p
 WHERE p.organization_id=org FOR UPDATE;
 IF NOT FOUND THEN
  RETURN QUERY SELECT 0::bigint,NULL::text,'UNPUBLISHED'::text;
  RETURN;
 END IF;
 SELECT m.* INTO selected FROM forge.gateway_catalog_selections m
 WHERE m.organization_id=org AND m.binding_id=pointer.router_binding_id
 AND m.catalog_revision=pointer.catalog_revision;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_UNAVAILABLE';
 END IF;
 RETURN QUERY SELECT pointer.catalog_revision,selected.default_alias,
  CASE WHEN gateway.binding_id=pointer.router_binding_id
   AND gateway.revision=selected.gateway_revision THEN 'CURRENT' ELSE 'STALE_GATEWAY' END;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.gateway_catalog_key(text,uuid),forge.gateway_status(text,uuid),
 forge.gateway_inference_candidates(text,uuid,text),forge.gateway_catalog_discovery(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.gateway_catalog_key(text,uuid),forge.gateway_status(text,uuid),
 forge.gateway_inference_candidates(text,uuid,text),forge.gateway_catalog_discovery(text,uuid) TO forge_gateway_service;

-- Rebinding: every company with a legacy gateway gets a profile carrying the same binding and revision, so its
-- snapshots, selections and discovery stay valid. Superuser context, as the 0025 backfill; nothing legacy is changed.
INSERT INTO forge.organization_gateway_profiles(organization_id,revision,binding_id,ceiling)
SELECT g.organization_id,g.revision,g.binding_id,NULL FROM forge.organization_gateways g
ON CONFLICT(organization_id) DO NOTHING;
COMMIT;
