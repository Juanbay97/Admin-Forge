-- Capability governance, storage 1/3: the platform-wide catalog, the platform default policy, the platform epoch and the
-- capability role pair. Additive and forward-only.
-- * forge_capability_authority (NOLOGIN) owns every governance SECURITY DEFINER function; forge_capability_service (the 7th
--   LOGIN pool, passworded by the operator like the others) holds no table privilege at all and may only EXECUTE them.
-- * The catalog and the platform policy are platform-global data, not tenant data: only the authority holds a grant, and only a
--   function (which re-validates a fresh verified platform owner, 0039) writes them. No role holds BYPASSRLS.
-- * The platform epoch is one monotonic counter bumped by every catalog or platform-policy change; per-company epochs live with
--   the company tables (0039). A client rejects a document whose epochs went down. No row means epoch 1: a migration seeds no data, so
--   the backup restore (data into a freshly migrated, empty database) stays valid; the first change writes epoch 2.
-- * ``attributes`` is a closed-size JSON object for connector transport, auth type, OAuth endpoints, MCP URL and egress hosts
--   (read by the connector broker); the application validates its shape, the database only bounds it.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_capability_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_capability_service NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_capability_service',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_capability_authority,forge_capability_service;

CREATE TABLE forge.capability_catalog (
 id text PRIMARY KEY CHECK(id ~ '^(tool|skill|connector|plugin|app):[a-z0-9][a-z0-9._-]{0,127}$'),
 kind text NOT NULL CHECK(kind IN ('tool','skill','connector','plugin','app') AND split_part(id,':',1)=kind),
 version text NOT NULL CHECK(length(version) BETWEEN 1 AND 64),
 risk text NOT NULL CHECK(risk IN ('low','medium','high')),
 is_base boolean NOT NULL,
 default_state text NOT NULL CHECK(default_state IN ('on','off')),
 min_sandbox_level integer NOT NULL CHECK(min_sandbox_level BETWEEN 0 AND 4),
 manifest_sha256 text CHECK(manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{64}$'),
 credential_locus text NOT NULL DEFAULT 'server' CHECK(credential_locus IN ('server','client','none')),
 declared_permissions text[] NOT NULL DEFAULT '{}' CHECK(cardinality(declared_permissions)<=16),
 granted_permissions text[] NOT NULL DEFAULT '{}' CHECK(cardinality(granted_permissions)<=16),
 attributes jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(attributes)='object' AND octet_length(attributes::text)<=4096),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 9223372036854775806),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(kind<>'app' OR default_state='off')
);

-- A platform default for one capability: an optional state and a lock. A forced-off lock beats every enable below it.
CREATE TABLE forge.capability_platform_policy (
 capability_id text PRIMARY KEY REFERENCES forge.capability_catalog(id),
 state text CHECK(state IS NULL OR state IN ('on','off')),
 lock text NOT NULL DEFAULT 'none' CHECK(lock IN ('none','forced_off')),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE forge.capability_platform_epoch (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 epoch bigint NOT NULL CHECK(epoch BETWEEN 2 AND 9223372036854775806)
);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['capability_catalog','capability_platform_policy','capability_platform_epoch'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service,forge_capability_service',t);
  EXECUTE format('CREATE POLICY capability_platform_scope ON forge.%I TO forge_capability_authority USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON forge.capability_catalog,forge.capability_platform_policy,forge.capability_platform_epoch
 TO forge_capability_authority;
RESET ROLE;
COMMIT;
