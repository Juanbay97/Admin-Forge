-- Capability governance, storage 3/3: the tool-invocation metadata log and its two write paths. Additive and forward-only.
-- * One row per tool, skill or connector invocation the member's device (``source='client'``) or the connector broker
--   (``source='broker'``) reports: who (the member), which capability, when, the outcome, the duration, the attestation level.
--   The event id is the identity, so a replayed batch stores nothing twice. Every text column is a closed grammar; there is NO
--   column that can hold arguments, output, a prompt, a path or any other content.
-- * ``cap_invocation_ingest`` is the only path for a member session: it re-validates the live session and active membership of the
--   named company, bounds the batch (at most 100 events), accepts exactly the allow-listed keys and stores the whole batch or nothing.
-- * ``cap_invocation_record_broker`` is the broker's path (``source='broker'``, with the MCP method, tool name, status and byte counts);
--   it is internal here and is granted to the broker authority by the connector-broker migration.
-- The authority holds SELECT and INSERT only (SELECT is what ON CONFLICT needs under row security); no role can update or delete a row.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.tool_invocation_log (
 event_id uuid PRIMARY KEY,
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 membership_id uuid NOT NULL,
 capability_id text NOT NULL CHECK(capability_id ~ '^([a-z]+:)?[a-z0-9][a-z0-9._-]{0,127}$'),
 at timestamptz NOT NULL,
 outcome text NOT NULL CHECK(outcome IN ('ok','error','denied','cancelled','timeout')),
 duration_ms integer NOT NULL CHECK(duration_ms BETWEEN 0 AND 86400000),
 sandbox_level integer CHECK(sandbox_level IS NULL OR sandbox_level BETWEEN 0 AND 4),
 source text NOT NULL DEFAULT 'client' CHECK(source IN ('client','broker')),
 method text CHECK(method IS NULL OR method ~ '^[a-z][a-z/_]{0,63}$'),
 tool_name text CHECK(tool_name IS NULL OR tool_name ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 status_code integer CHECK(status_code IS NULL OR status_code BETWEEN 100 AND 599),
 bytes_in bigint CHECK(bytes_in IS NULL OR bytes_in BETWEEN 0 AND 1000000000),
 bytes_out bigint CHECK(bytes_out IS NULL OR bytes_out BETWEEN 0 AND 1000000000),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id)
);
CREATE INDEX tool_invocation_log_by_company ON forge.tool_invocation_log(organization_id,recorded_at);
ALTER TABLE forge.tool_invocation_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.tool_invocation_log FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.tool_invocation_log FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service,forge_capability_service;
CREATE POLICY capability_org_scope ON forge.tool_invocation_log TO forge_capability_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization')) WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization'));
GRANT SELECT,INSERT ON forge.tool_invocation_log TO forge_capability_authority;
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_capability_authority;
SET LOCAL ROLE forge_capability_authority;

CREATE FUNCTION forge.cap_invocation_ingest(digest text,org uuid,events jsonb) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; item jsonb; stored integer:=0; added integer; seen text[]:=ARRAY[]::text[];
BEGIN
 member:=forge.cap_lock_member(digest,org);
 PERFORM set_config('forge.organization',org::text,true);
 IF events IS NULL OR jsonb_typeof(events)<>'array' OR jsonb_array_length(events) NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(events) LOOP
  IF jsonb_typeof(item)<>'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(item) k
     WHERE k NOT IN ('event_id','capability_id','at','outcome','duration_ms','sandbox_level'))
   OR NOT (item ?& ARRAY['event_id','capability_id','at','outcome','duration_ms'])
   OR (item->>'at') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$' THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
  END IF;
  BEGIN
   INSERT INTO forge.tool_invocation_log(event_id,organization_id,membership_id,capability_id,at,outcome,duration_ms,sandbox_level)
   VALUES((item->>'event_id')::uuid,org,member,item->>'capability_id',(item->>'at')::timestamptz,item->>'outcome',
    (item->>'duration_ms')::integer,(item->>'sandbox_level')::integer)
   ON CONFLICT(event_id) DO NOTHING;
   GET DIAGNOSTICS added=ROW_COUNT;
   stored:=stored+added;
  EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
  END;
 END LOOP;
 RETURN stored;
END $$;

CREATE FUNCTION forge.cap_invocation_record_broker(org uuid,member uuid,event uuid,capability text,result text,took integer,rpc text,
 tool text,sent bigint,received bigint,status integer) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE added integer;
BEGIN
 IF org IS NULL OR member IS NULL OR event IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID'; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 BEGIN
  INSERT INTO forge.tool_invocation_log(event_id,organization_id,membership_id,capability_id,at,outcome,duration_ms,source,method,
   tool_name,status_code,bytes_in,bytes_out)
  VALUES(event,org,member,capability,clock_timestamp(),result,took,'broker',rpc,tool,status,sent,received)
  ON CONFLICT(event_id) DO NOTHING;
  GET DIAGNOSTICS added=ROW_COUNT;
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END;
 RETURN added=1;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_capability_authority;
REVOKE ALL ON FUNCTION forge.cap_invocation_ingest(text,uuid,jsonb),
 forge.cap_invocation_record_broker(uuid,uuid,uuid,text,text,integer,text,text,bigint,bigint,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.cap_invocation_ingest(text,uuid,jsonb) TO forge_capability_service;
COMMIT;
