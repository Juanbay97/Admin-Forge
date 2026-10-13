-- Versioned model prices and the cost snapshot on each usage event. Additive and forward-only.
-- * model_prices: the platform sets input and output prices per upstream model as integer micro-USD per million tokens. A change
--   is a new version (never an update), effective from a time, audited, and never rewrites an event already recorded.
-- * usage_record now snapshots the price in force when the event is written (price_id and cost_micros, rounded half up); a model
--   with no price in force leaves both NULL and is counted as unpriced in the rollup, never reported as free.
-- * Only the platform authority writes prices (fresh verified owner); the recording authority only reads them; no login role has
--   any table privilege.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.model_prices (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 upstream_id text NOT NULL CHECK(upstream_id ~ '^[!-~]{1,255}$'),
 version integer NOT NULL CHECK(version>=1),
 input_micros bigint NOT NULL CHECK(input_micros BETWEEN 0 AND 1000000000),
 output_micros bigint NOT NULL CHECK(output_micros BETWEEN 0 AND 1000000000),
 currency text NOT NULL DEFAULT 'USD' CHECK(currency ~ '^[A-Z]{3}$'),
 effective_from timestamptz NOT NULL,
 set_by uuid NOT NULL REFERENCES forge.owned_accounts(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(upstream_id,version)
);
ALTER TABLE forge.usage_events ADD CONSTRAINT usage_events_price_fk FOREIGN KEY(price_id) REFERENCES forge.model_prices(id);
ALTER TABLE forge.model_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.model_prices FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.model_prices FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service;
CREATE POLICY platform_scope ON forge.model_prices TO forge_platform_authority USING(true) WITH CHECK(true);
CREATE POLICY price_read ON forge.model_prices FOR SELECT TO forge_gateway_authority USING(true);
GRANT SELECT,INSERT ON forge.model_prices TO forge_platform_authority;
GRANT SELECT ON forge.model_prices TO forge_gateway_authority;
ALTER TABLE forge.platform_audit_log DROP CONSTRAINT platform_audit_log_action_check;
ALTER TABLE forge.platform_audit_log ADD CONSTRAINT platform_audit_log_action_check CHECK(action IN
 ('company.created','company.suspended','company.reactivated','company.branding_saved','owner.mfa_enrolled',
  'owner.mfa_recovery_used','gateway_key.created','gateway_key.rotated','gateway_key.status_changed',
  'company.gateway_assigned','company.model_access_set','model_price.set'));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;
CREATE OR REPLACE FUNCTION forge.usage_record(org uuid,member uuid,event uuid,alias_name text,upstream text,kid uuid,
 prompt bigint,completion bigint,latency integer,first_byte integer,outcome text,failure text,source text)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE written integer; day_utc date; price record; cost bigint;
BEGIN
 IF org IS NULL OR member IS NULL OR event IS NULL OR source IS NULL OR outcome IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='USAGE_INVALID';
 END IF;
 PERFORM set_config('forge.organization',org::text,true);
 day_utc:=(clock_timestamp() AT TIME ZONE 'UTC')::date;
 BEGIN
  -- The price in force now is snapshotted on the event; no price in force means unpriced (NULL), never zero.
  SELECT p.id AS price_id,p.input_micros,p.output_micros INTO price FROM forge.model_prices p
   WHERE p.upstream_id=upstream AND p.effective_from<=clock_timestamp() ORDER BY p.effective_from DESC,p.version DESC LIMIT 1;
  IF FOUND AND prompt>=0 AND completion>=0 THEN
   cost:=round((prompt::numeric*price.input_micros+completion::numeric*price.output_micros)/1000000)::bigint;
  END IF;
  INSERT INTO forge.usage_events(event_id,organization_id,membership_id,model_alias,upstream_id,key_id,prompt_tokens,
   completion_tokens,latency_ms,ttfb_ms,status,error_code,usage_source,price_id,cost_micros)
  VALUES(event,org,member,alias_name,upstream,kid,prompt,completion,latency,first_byte,outcome,failure,source,
   CASE WHEN cost IS NULL THEN NULL ELSE price.price_id END,cost)
  ON CONFLICT(event_id) DO NOTHING;
  GET DIAGNOSTICS written=ROW_COUNT;
  IF written=0 THEN RETURN false; END IF;
  INSERT INTO forge.usage_daily(day,organization_id,membership_id,upstream_id,key_id,requests,prompt_tokens,
   completion_tokens,estimated_requests,error_requests,cost_micros,unpriced_requests)
  VALUES(day_utc,org,member,upstream,coalesce(kid,'00000000-0000-0000-0000-000000000000'::uuid),1,prompt,completion,
   CASE WHEN source='estimated' THEN 1 ELSE 0 END,CASE WHEN outcome='error' THEN 1 ELSE 0 END,
   coalesce(cost,0),CASE WHEN cost IS NULL THEN 1 ELSE 0 END)
  ON CONFLICT(day,organization_id,membership_id,upstream_id,key_id) DO UPDATE SET
   requests=forge.usage_daily.requests+1,
   prompt_tokens=forge.usage_daily.prompt_tokens+excluded.prompt_tokens,
   completion_tokens=forge.usage_daily.completion_tokens+excluded.completion_tokens,
   estimated_requests=forge.usage_daily.estimated_requests+excluded.estimated_requests,
   error_requests=forge.usage_daily.error_requests+excluded.error_requests,
   cost_micros=forge.usage_daily.cost_micros+excluded.cost_micros,
   unpriced_requests=forge.usage_daily.unpriced_requests+excluded.unpriced_requests;
 EXCEPTION WHEN check_violation OR foreign_key_violation OR not_null_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='USAGE_INVALID';
 END;
 RETURN true;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;
-- A new version of one model's price: version = highest + 1 (serialized per model), effective from ``starts`` (default now).
CREATE FUNCTION forge.platform_price_set(digest text,upstream text,input_price bigint,output_price bigint,starts timestamptz)
RETURNS TABLE(id bigint,upstream_id text,version integer,input_micros bigint,output_micros bigint,currency text,
 effective_from timestamptz,set_by uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; next_version integer; written bigint;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF upstream IS NULL OR input_price IS NULL OR output_price IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('forge.price:'||upstream,0));
 SELECT coalesce(max(p.version),0)+1 INTO next_version FROM forge.model_prices p WHERE p.upstream_id=upstream;
 BEGIN
  INSERT INTO forge.model_prices(upstream_id,version,input_micros,output_micros,effective_from,set_by)
  VALUES(upstream,next_version,input_price,output_price,coalesce(starts,clock_timestamp()),actor) RETURNING forge.model_prices.id INTO written;
 EXCEPTION WHEN check_violation THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END;
 PERFORM forge.platform_audit_write(actor,'model_price.set',NULL,NULL);
 RETURN QUERY SELECT p.id,p.upstream_id,p.version,p.input_micros,p.output_micros,p.currency,p.effective_from,p.set_by
  FROM forge.model_prices p WHERE p.id=written;
END $$;

CREATE FUNCTION forge.platform_price_list(digest text,upstream text)
RETURNS TABLE(id bigint,upstream_id text,version integer,input_micros bigint,output_micros bigint,currency text,
 effective_from timestamptz,set_by uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 RETURN QUERY SELECT p.id,p.upstream_id,p.version,p.input_micros,p.output_micros,p.currency,p.effective_from,p.set_by
  FROM forge.model_prices p WHERE upstream IS NULL OR p.upstream_id=upstream ORDER BY p.upstream_id,p.version DESC LIMIT 500;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_price_set(text,text,bigint,bigint,timestamptz),forge.platform_price_list(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_price_set(text,text,bigint,bigint,timestamptz),forge.platform_price_list(text,text)
 TO forge_platform_service;
COMMIT;
