-- Opt-in owned gateway catalogue; reviewed existing profiles remain unchanged.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
-- Evolve only the payload version correlation check, never immutable prior files.
DO $$ DECLARE c text; BEGIN
 SELECT conname INTO STRICT c FROM pg_constraint
 WHERE conrelid='forge.model_catalog_snapshots'::regclass AND contype='c'
 AND pg_get_constraintdef(oid) LIKE '%schema_version%';
 EXECUTE format('ALTER TABLE forge.model_catalog_snapshots DROP CONSTRAINT %I',c);
END $$;
ALTER TABLE forge.model_catalog_snapshots ADD CONSTRAINT catalog_payload_version CHECK (
 (payload::jsonb->>'schema_version')::integer IN (1,2)
 AND payload::jsonb->>'organization_id'=organization_id::text
 AND payload::jsonb->>'router_binding_id'=router_binding_id::text
 AND (payload::jsonb->>'revision')::bigint=revision
 AND jsonb_typeof(payload::jsonb->'aliases')='array'
);
CREATE TABLE forge.gateway_model_discoveries (
 organization_id uuid PRIMARY KEY REFERENCES forge.organizations(id),
 gateway_revision bigint NOT NULL CHECK(gateway_revision>0),
 binding_id uuid NOT NULL,
 model_ids jsonb NOT NULL CHECK(jsonb_typeof(model_ids)='array' AND jsonb_array_length(model_ids) BETWEEN 1 AND 500),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE forge.gateway_catalog_selections (
 organization_id uuid NOT NULL,
 binding_id uuid NOT NULL,
 catalog_revision bigint NOT NULL,
 gateway_revision bigint NOT NULL CHECK(gateway_revision>0),
 default_alias text NOT NULL CHECK(default_alias ~ '^[a-z][a-z0-9_-]{0,63}$'),
 private_mapping jsonb NOT NULL CHECK(jsonb_typeof(private_mapping)='object'),
 selection_sha256 text NOT NULL CHECK(selection_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(organization_id,binding_id,catalog_revision),
 FOREIGN KEY(organization_id,binding_id,catalog_revision)
 REFERENCES forge.model_catalog_snapshots(organization_id,router_binding_id,revision)
);
ALTER TABLE forge.catalog_publication_operations ADD COLUMN gateway_revision bigint;
ALTER TABLE forge.catalog_publication_operations ADD COLUMN selection_sha256 text;
ALTER TABLE forge.catalog_publication_operations ADD CONSTRAINT owned_catalog_replay
 CHECK((gateway_revision IS NULL AND selection_sha256 IS NULL)
 OR (gateway_revision>0 AND selection_sha256 ~ '^[0-9a-f]{64}$'));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['gateway_model_discoveries','gateway_catalog_selections'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_account_service,forge_gateway_service',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['gateway_model_discoveries','gateway_catalog_selections',
   'model_catalog_snapshots','active_model_catalogs','catalog_publication_operations','outbox_events'] LOOP
  EXECUTE format('CREATE POLICY owned_catalog_scope ON forge.%I TO forge_gateway_authority USING (organization_id=forge.enrollment_uuid(''forge.organization'')) WITH CHECK (organization_id=forge.enrollment_uuid(''forge.organization''))',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON forge.gateway_model_discoveries,forge.active_model_catalogs TO forge_gateway_authority;
GRANT SELECT,INSERT ON forge.gateway_catalog_selections,forge.model_catalog_snapshots,
 forge.catalog_publication_operations TO forge_gateway_authority;
GRANT INSERT ON forge.outbox_events TO forge_gateway_authority;

CREATE FUNCTION forge.gateway_resolve_member(org uuid,account uuid) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; enabled boolean;
BEGIN
 PERFORM set_config('forge.organization',org::text,true);
 SELECT active INTO enabled FROM forge.organizations WHERE id=org FOR UPDATE;
 IF NOT FOUND OR NOT enabled THEN RETURN NULL; END IF;
 SELECT m.id INTO member FROM forge.memberships m WHERE m.organization_id=org
  AND m.identity_id=account AND m.status='active' FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM set_config('forge.enrollment_actor',account::text,true);
 PERFORM 1 FROM forge.identities WHERE id=account AND provider='forge'
  AND issuer='urn:prometheon:forge:accounts:v1' AND subject=account::text
  AND entra_tenant_id IS NULL AND entra_object_id IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN member;
END $$;
RESET ROLE;
ALTER FUNCTION forge.gateway_resolve_member(uuid,uuid) OWNER TO forge_enrollment_authority;
REVOKE ALL ON FUNCTION forge.gateway_resolve_member(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.gateway_resolve_member(uuid,uuid) TO forge_gateway_authority;
SET LOCAL ROLE forge_migrator;

CREATE FUNCTION forge.gateway_catalog_refresh(digest text,org uuid,expected bigint,binding uuid,ids jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g record;
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 SELECT * INTO g FROM forge.organization_gateways WHERE organization_id=org FOR UPDATE;
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

CREATE FUNCTION forge.gateway_catalog_discovery(digest text,org uuid)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text,model_ids jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.gateway_lock_admin(digest,org);
 RETURN QUERY SELECT g.revision,g.binding_id,g.endpoint,g.encrypted_key,d.model_ids
 FROM forge.organization_gateways g JOIN forge.gateway_model_discoveries d
 ON d.organization_id=g.organization_id AND d.binding_id=g.binding_id AND d.gateway_revision=g.revision
 WHERE g.organization_id=org;
END $$;

CREATE FUNCTION forge.gateway_catalog_publish(digest text,org uuid,operation uuid,expected bigint,
 gateway_revision bigint,binding uuid,mapping jsonb,default_alias text,payload text,checksum text,selection_hash text)
RETURNS bigint LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; member uuid; g record; d record; prior record; current_revision bigint; event uuid;
BEGIN
 account:=forge.gateway_lock_admin(digest,org);
 member:=forge.gateway_resolve_member(org,account);
 IF member IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED'; END IF;
 SELECT * INTO g FROM forge.organization_gateways WHERE organization_id=org FOR UPDATE;
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

CREATE FUNCTION forge.gateway_catalog_member(digest text,org uuid)
RETURNS TABLE(payload text,payload_sha256 text,default_alias text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR forge.gateway_resolve_member(org,account) IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 RETURN QUERY SELECT s.payload,s.payload_sha256,m.default_alias FROM forge.active_model_catalogs p
 JOIN forge.organization_gateways g ON g.organization_id=p.organization_id AND g.binding_id=p.router_binding_id
 JOIN forge.gateway_catalog_selections m ON m.organization_id=p.organization_id AND m.binding_id=p.router_binding_id
  AND m.catalog_revision=p.catalog_revision AND m.gateway_revision=g.revision
 JOIN forge.model_catalog_snapshots s ON s.organization_id=p.organization_id AND s.router_binding_id=p.router_binding_id
  AND s.revision=p.catalog_revision WHERE p.organization_id=org;
END $$;
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
RESET ROLE;
DO $$ DECLARE f record; BEGIN
 FOR f IN SELECT p.oid::regprocedure::text AS signature FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='forge'
 AND p.proname IN ('gateway_catalog_refresh','gateway_catalog_discovery','gateway_catalog_publish','gateway_catalog_member') LOOP
  EXECUTE format('ALTER FUNCTION %s OWNER TO forge_gateway_authority',f.signature);
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO forge_gateway_service',f.signature);
 END LOOP;
END $$;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
COMMIT;
