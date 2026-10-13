-- Usage metering storage: one event per inference that reached the gateway and a daily rollup kept in the same transaction.
-- Additive and forward-only.
-- * usage_events holds counters, timings, status and the serving key; it has NO content column (no prompt, no response).
--   Its identity is a caller-generated event id, so a retried write is idempotent. price_id and cost_micros stay NULL until
--   prices exist (0036); an event without a price is unpriced, never zero-cost.
-- * usage_daily is the UTC-day rollup per company, member, upstream model and key (the all-zero key id stands for the legacy key).
--   usage_record is the only write path: a DEFINER function owned by forge_gateway_authority and executable by the service pool,
--   which holds no table privilege at all (it records, it never reads). The member is bound to the company by a composite key.
-- * gateway_inference_candidates now also returns the member that was authorized, so the application can attribute the event
--   without a live session (a stream may outlive a logout, and its usage must still be recorded).
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.usage_events (
 event_id uuid PRIMARY KEY,
 organization_id uuid NOT NULL,
 membership_id uuid NOT NULL,
 model_alias text NOT NULL CHECK(model_alias ~ '^[a-z][a-z0-9_-]{0,63}$'),
 upstream_id text NOT NULL CHECK(upstream_id ~ '^[!-~]{1,255}$'),
 key_id uuid REFERENCES forge.gateway_keys(id),
 prompt_tokens bigint NOT NULL CHECK(prompt_tokens BETWEEN 0 AND 1000000000000),
 completion_tokens bigint NOT NULL CHECK(completion_tokens BETWEEN 0 AND 1000000000000),
 latency_ms integer NOT NULL CHECK(latency_ms>=0),
 ttfb_ms integer CHECK(ttfb_ms IS NULL OR ttfb_ms>=0),
 status text NOT NULL CHECK(status IN ('ok','cancelled','error')),
 error_code text CHECK(error_code IS NULL OR error_code ~ '^[A-Z][A-Z_]{0,63}$'),
 usage_source text NOT NULL CHECK(usage_source IN ('gateway','estimated')),
 price_id bigint,
 cost_micros bigint CHECK(cost_micros IS NULL OR cost_micros>=0),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id)
);
CREATE INDEX usage_events_by_company ON forge.usage_events(organization_id,recorded_at);
CREATE TABLE forge.usage_daily (
 day date NOT NULL,
 organization_id uuid NOT NULL,
 membership_id uuid NOT NULL,
 upstream_id text NOT NULL,
 key_id uuid NOT NULL,
 requests bigint NOT NULL DEFAULT 0,
 prompt_tokens bigint NOT NULL DEFAULT 0,
 completion_tokens bigint NOT NULL DEFAULT 0,
 estimated_requests bigint NOT NULL DEFAULT 0,
 error_requests bigint NOT NULL DEFAULT 0,
 cost_micros bigint NOT NULL DEFAULT 0,
 unpriced_requests bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(day,organization_id,membership_id,upstream_id,key_id),
 FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id)
);
CREATE INDEX usage_daily_by_company ON forge.usage_daily(organization_id,day);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['usage_events','usage_daily'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service',t);
  EXECUTE format('CREATE POLICY usage_scope ON forge.%I TO forge_gateway_authority USING(organization_id=forge.enrollment_uuid(''forge.organization'')) WITH CHECK(organization_id=forge.enrollment_uuid(''forge.organization''))',t);
 END LOOP;
END $$;
-- SELECT is what ON CONFLICT needs under row security; only the authority (never the service pool) holds it.
GRANT SELECT,INSERT ON forge.usage_events TO forge_gateway_authority;
GRANT SELECT,INSERT,UPDATE ON forge.usage_daily TO forge_gateway_authority;
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;

CREATE FUNCTION forge.usage_record(org uuid,member uuid,event uuid,alias_name text,upstream text,kid uuid,
 prompt bigint,completion bigint,latency integer,first_byte integer,outcome text,failure text,source text)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE written integer; day_utc date;
BEGIN
 IF org IS NULL OR member IS NULL OR event IS NULL OR source IS NULL OR outcome IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='USAGE_INVALID';
 END IF;
 PERFORM set_config('forge.organization',org::text,true);
 day_utc:=(clock_timestamp() AT TIME ZONE 'UTC')::date;
 BEGIN
  INSERT INTO forge.usage_events(event_id,organization_id,membership_id,model_alias,upstream_id,key_id,prompt_tokens,
   completion_tokens,latency_ms,ttfb_ms,status,error_code,usage_source)
  VALUES(event,org,member,alias_name,upstream,kid,prompt,completion,latency,first_byte,outcome,failure,source)
  ON CONFLICT(event_id) DO NOTHING;
  GET DIAGNOSTICS written=ROW_COUNT;
  IF written=0 THEN RETURN false; END IF;
  INSERT INTO forge.usage_daily(day,organization_id,membership_id,upstream_id,key_id,requests,prompt_tokens,
   completion_tokens,estimated_requests,error_requests,unpriced_requests)
  VALUES(day_utc,org,member,upstream,coalesce(kid,'00000000-0000-0000-0000-000000000000'::uuid),1,prompt,completion,
   CASE WHEN source='estimated' THEN 1 ELSE 0 END,CASE WHEN outcome='error' THEN 1 ELSE 0 END,1)
  ON CONFLICT(day,organization_id,membership_id,upstream_id,key_id) DO UPDATE SET
   requests=forge.usage_daily.requests+1,
   prompt_tokens=forge.usage_daily.prompt_tokens+excluded.prompt_tokens,
   completion_tokens=forge.usage_daily.completion_tokens+excluded.completion_tokens,
   estimated_requests=forge.usage_daily.estimated_requests+excluded.estimated_requests,
   error_requests=forge.usage_daily.error_requests+excluded.error_requests,
   unpriced_requests=forge.usage_daily.unpriced_requests+excluded.unpriced_requests;
 EXCEPTION WHEN check_violation OR foreign_key_violation OR not_null_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='USAGE_INVALID';
 END;
 RETURN true;
END $$;

-- The return type gains the authorized member, so the 0033 function is replaced rather than altered.
DROP FUNCTION forge.gateway_inference_candidates(text,uuid,text);
CREATE FUNCTION forge.gateway_inference_candidates(digest text,org uuid,alias text)
RETURNS TABLE(catalog_revision bigint,upstream_id text,gateway_revision bigint,binding_id uuid,endpoint text,
 encrypted_key text,key_id uuid,key_revision bigint,membership_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; member uuid; prof record; chosen record;
BEGIN
 account:=forge.account_validate_session(digest);
 member:=CASE WHEN account IS NULL THEN NULL ELSE forge.gateway_resolve_member(org,account) END;
 IF member IS NULL OR alias IS NULL OR alias !~ '^[a-z][a-z0-9_-]{0,63}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
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
 RETURN QUERY SELECT chosen.revision,chosen.upstream,prof.revision,prof.binding_id,k.origin,k.encrypted_key,k.id,k.revision,member
  FROM forge.organization_gateway_keys a
  JOIN forge.gateway_keys k ON k.id=a.key_id AND k.status='active' AND k.encrypted_key IS NOT NULL
  WHERE a.organization_id=org AND a.active ORDER BY a.priority;
 IF NOT FOUND AND NOT EXISTS(SELECT 1 FROM forge.organization_gateway_keys a WHERE a.organization_id=org) THEN
  RETURN QUERY SELECT chosen.revision,chosen.upstream,prof.revision,prof.binding_id,g.endpoint,g.encrypted_key,NULL::uuid,NULL::bigint,member
   FROM forge.organization_gateways g WHERE g.organization_id=org AND g.binding_id=prof.binding_id;
 END IF;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED'; END IF;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.usage_record(uuid,uuid,uuid,text,text,uuid,bigint,bigint,integer,integer,text,text,text),
 forge.gateway_inference_candidates(text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.usage_record(uuid,uuid,uuid,text,text,uuid,bigint,bigint,integer,integer,text,text,text),
 forge.gateway_inference_candidates(text,uuid,text) TO forge_gateway_service;
COMMIT;
