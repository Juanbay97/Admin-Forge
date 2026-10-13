-- Client attestation reports. Additive and forward-only.
-- * One row per report the member's device sends after its sandbox self-test: the attested level (0..4), the suite, client and OS build
--   identifiers and the per-case pass/fail list. Every text column is a closed grammar and the cases are ``{id, passed}`` pairs: there is
--   NO column that can hold a path, an environment value, a prompt or any other content. The report is client-asserted, advisory telemetry.
-- * ``cap_attestation_ingest`` is the only write path: it re-validates the live session and the active membership of the named company,
--   accepts exactly the allow-listed keys, stores the whole report or nothing, treats the same device time as a replay (nothing stored) and
--   keeps at most 24 reports per member per day (the rest are not stored). The member always comes from the session, never the payload.
-- * ``cap_latest_attestation`` returns the member's newest level for the company, or NULL when there is none or the newest is older
--   than 30 days; the effective policy uses it so the server no longer relies only on the level a request claims.
-- The log is append-only by privilege (SELECT and INSERT only, no role can update or delete) and is the audit trail of what each device
-- reported and when (the server's own clock stamps ``recorded_at``).
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.client_attestations (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 membership_id uuid NOT NULL,
 level integer NOT NULL CHECK(level BETWEEN 0 AND 4),
 suite_version text NOT NULL CHECK(suite_version ~ '^[A-Za-z0-9._-]{1,32}$'),
 client_version text NOT NULL CHECK(client_version ~ '^[A-Za-z0-9._+-]{1,32}$'),
 os_build text NOT NULL CHECK(os_build ~ '^[A-Za-z0-9._ -]{1,64}$'),
 cases jsonb NOT NULL CHECK(jsonb_typeof(cases)='array' AND jsonb_array_length(cases)<=64),
 reported_at timestamptz NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id),
 UNIQUE(membership_id,reported_at)
);
CREATE INDEX client_attestations_latest ON forge.client_attestations(organization_id,membership_id,recorded_at);
ALTER TABLE forge.client_attestations ENABLE ROW LEVEL SECURITY;
ALTER TABLE forge.client_attestations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON forge.client_attestations FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service,forge_capability_service;
CREATE POLICY capability_org_scope ON forge.client_attestations TO forge_capability_authority
 USING(organization_id=forge.enrollment_uuid('forge.organization')) WITH CHECK(organization_id=forge.enrollment_uuid('forge.organization'));
GRANT SELECT,INSERT ON forge.client_attestations TO forge_capability_authority;
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_capability_authority;
SET LOCAL ROLE forge_capability_authority;

CREATE FUNCTION forge.cap_attestation_ingest(digest text,org uuid,report jsonb) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; item jsonb; added integer;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 PERFORM set_config('forge.organization',org::text,true);
 IF report IS NULL OR jsonb_typeof(report)<>'object'
  OR EXISTS(SELECT 1 FROM jsonb_object_keys(report) k WHERE k NOT IN ('level','suite_version','client_version','os_build','cases','at'))
  OR NOT (report ?& ARRAY['level','suite_version','client_version','os_build','cases','at'])
  OR jsonb_typeof(report->'level')<>'number' OR jsonb_typeof(report->'suite_version')<>'string'
  OR jsonb_typeof(report->'client_version')<>'string' OR jsonb_typeof(report->'os_build')<>'string'
  OR jsonb_typeof(report->'cases')<>'array' OR jsonb_array_length(report->'cases')>64 OR jsonb_typeof(report->'at')<>'string'
  OR (report->>'at') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(report->'cases') LOOP
  IF jsonb_typeof(item)<>'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(item) k WHERE k NOT IN ('id','passed'))
   OR NOT (item ?& ARRAY['id','passed']) OR jsonb_typeof(item->'passed')<>'boolean' OR jsonb_typeof(item->'id')<>'string'
   OR (item->>'id') !~ '^[a-z0-9][a-z0-9_.-]{0,63}$' THEN
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
  END IF;
 END LOOP;
 IF (SELECT count(*) FROM forge.client_attestations a WHERE a.membership_id=member AND a.recorded_at>clock_timestamp()-interval '1 day')>=24 THEN
  RETURN false;
 END IF;
 BEGIN
  INSERT INTO forge.client_attestations(organization_id,membership_id,level,suite_version,client_version,os_build,cases,reported_at)
  VALUES(org,member,(report->>'level')::integer,report->>'suite_version',report->>'client_version',report->>'os_build',report->'cases',
   (report->>'at')::timestamptz)
  ON CONFLICT(membership_id,reported_at) DO NOTHING;
  GET DIAGNOSTICS added=ROW_COUNT;
 EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CAP_INVALID';
 END;
 RETURN added=1;
END $$;

CREATE FUNCTION forge.cap_latest_attestation(digest text,org uuid) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member uuid; found integer;
BEGIN
 member:=forge.cap_lock_member(digest,org);
 PERFORM set_config('forge.organization',org::text,true);
 SELECT a.level INTO found FROM forge.client_attestations a
  WHERE a.organization_id=org AND a.membership_id=member AND a.recorded_at>clock_timestamp()-interval '30 days'
  ORDER BY a.recorded_at DESC,a.id DESC LIMIT 1;
 RETURN found;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_capability_authority;
REVOKE ALL ON FUNCTION forge.cap_attestation_ingest(text,uuid,jsonb),forge.cap_latest_attestation(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.cap_attestation_ingest(text,uuid,jsonb),forge.cap_latest_attestation(text,uuid) TO forge_capability_service;
COMMIT;
