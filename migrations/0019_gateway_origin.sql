-- Additive per-organization gateway origin; never applied to an existing demo implicitly.
-- The deployment allow-list in the application is the authority. The database only keeps
-- defense in depth: the fixed production origin or numeric loopback http with a port.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
ALTER TABLE forge.organization_gateways DROP CONSTRAINT organization_gateways_endpoint_check;
ALTER TABLE forge.organization_gateways ADD CONSTRAINT organization_gateways_endpoint_check
 CHECK(endpoint='https://ia.prometheonlab.com'
  OR endpoint ~ '^http://127\.0\.0\.1:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$');
RESET ROLE;

-- Functions are created by the existing authority owner under a temporary schema grant,
-- the same boundary 0015 used. Existing rows keep their fixed origin and ciphertext.
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
SET LOCAL ROLE forge_gateway_authority;

CREATE FUNCTION forge.gateway_save(digest text,org uuid,expected bigint,binding uuid,payload text,origin text)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.gateway_lock_admin(digest,org);
 IF expected IS NULL OR expected<0 OR expected>9223372036854775805
  OR binding IS NULL OR payload IS NULL OR length(payload) NOT BETWEEN 100 AND 12288
  OR origin IS NULL OR NOT (origin='https://ia.prometheonlab.com'
   OR origin ~ '^http://127\.0\.0\.1:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$') THEN
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

-- The original five-argument entry point keeps its contract but now always means the
-- fixed default origin, so a ciphertext sealed for it can never sit beside another origin.
CREATE OR REPLACE FUNCTION forge.gateway_save(digest text,org uuid,expected bigint,binding uuid,payload text)
RETURNS TABLE(revision bigint,binding_id uuid,endpoint text,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 RETURN QUERY SELECT s.revision,s.binding_id,s.endpoint,s.encrypted_key
  FROM forge.gateway_save(digest,org,expected,binding,payload,'https://ia.prometheonlab.com') s;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.gateway_save(text,uuid,bigint,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.gateway_save(text,uuid,bigint,uuid,text,text) TO forge_gateway_service;
COMMIT;
