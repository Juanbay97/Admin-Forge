-- Additive: the database no longer pins the gateway origin to one spelling. The deployment
-- allow-list in the application (FORGE_GATEWAY_ORIGINS) is the authority; the database keeps
-- defense in depth by accepting only a canonical origin: any lowercase https host name with an
-- optional port (no userinfo, path, query, fragment or numeric IPv4 host), or the numeric
-- loopback http dev origin with an explicit port. Existing rows and ciphertexts are untouched.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
ALTER TABLE forge.organization_gateways DROP CONSTRAINT organization_gateways_endpoint_check;
ALTER TABLE forge.organization_gateways ADD CONSTRAINT organization_gateways_endpoint_check
 CHECK(length(endpoint)<=255 AND (
  (endpoint ~ '^https://[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?$'
   AND endpoint !~ '^https://[0-9]+(\.[0-9]+){3}(:|$)')
  OR endpoint ~ '^http://127\.0\.0\.1:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$'));
RESET ROLE;

-- The six-argument function is replaced by its authority owner under a temporary schema
-- grant, the same boundary 0015 and 0019 used. Its signature, owner, search_path and EXECUTE
-- grants are unchanged; only the origin predicate widens, in step with the CHECK above.
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;

CREATE OR REPLACE FUNCTION forge.gateway_save(digest text,org uuid,expected bigint,binding uuid,payload text,origin text)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.gateway_lock_admin(digest,org);
 IF expected IS NULL OR expected<0 OR expected>9223372036854775805
  OR binding IS NULL OR payload IS NULL OR length(payload) NOT BETWEEN 100 AND 12288
  OR origin IS NULL OR NOT (length(origin)<=255 AND (
   (origin ~ '^https://[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?$'
    AND origin !~ '^https://[0-9]+(\.[0-9]+){3}(:|$)')
   OR origin ~ '^http://127\.0\.0\.1:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$')) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_INVALID';
 END IF;
 SELECT g.revision INTO current_revision FROM forge.organization_gateways g
  WHERE g.organization_id=org FOR UPDATE;
 IF coalesce(current_revision,0)<>expected THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_CONFLICT';
 END IF;
 INSERT INTO forge.organization_gateways(organization_id,revision,binding_id,endpoint,encrypted_key,updated_by)
 VALUES(org,expected+1,binding,origin,payload,actor)
 ON CONFLICT(organization_id) DO UPDATE SET revision=excluded.revision,
  binding_id=excluded.binding_id,endpoint=excluded.endpoint,encrypted_key=excluded.encrypted_key,
  updated_by=excluded.updated_by,updated_at=clock_timestamp();
 INSERT INTO forge.gateway_configuration_audit(organization_id,revision,actor_id)
 VALUES(org,expected+1,actor);
 RETURN QUERY SELECT g.revision,g.binding_id,g.endpoint,g.encrypted_key
  FROM forge.organization_gateways g WHERE g.organization_id=org;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
COMMIT;
