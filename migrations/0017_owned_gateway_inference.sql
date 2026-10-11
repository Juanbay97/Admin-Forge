-- Opt-in member text inference; prior account/catalogue profiles remain exact.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
CREATE FUNCTION forge.gateway_inference_route(digest text,org uuid,alias text)
RETURNS TABLE(catalog_revision bigint,upstream_id text,gateway_revision bigint,
 binding_id uuid,endpoint text,encrypted_key text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR forge.gateway_resolve_member(org,account) IS NULL
  OR alias IS NULL OR alias !~ '^[a-z][a-z0-9_-]{0,63}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
 -- The member helper locks current organization/account/member authority.
 -- Resolve only the active immutable snapshot and exact current gateway binding.
 RETURN QUERY SELECT p.catalog_revision,m.private_mapping->>alias,g.revision,
  g.binding_id,g.endpoint,g.encrypted_key
 FROM forge.active_model_catalogs p
 JOIN forge.organization_gateways g ON g.organization_id=p.organization_id
  AND g.binding_id=p.router_binding_id
 JOIN forge.gateway_catalog_selections m ON m.organization_id=p.organization_id
  AND m.binding_id=p.router_binding_id AND m.catalog_revision=p.catalog_revision
  AND m.gateway_revision=g.revision
 JOIN forge.model_catalog_snapshots s ON s.organization_id=p.organization_id
  AND s.router_binding_id=p.router_binding_id AND s.revision=p.catalog_revision
 WHERE p.organization_id=org AND m.private_mapping ? alias
  AND (m.private_mapping->>alias) ~ '^[!-~]{1,255}$';
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='GATEWAY_DENIED';
 END IF;
END $$;
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
RESET ROLE;
ALTER FUNCTION forge.gateway_inference_route(text,uuid,text) OWNER TO forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.gateway_inference_route(text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.gateway_inference_route(text,uuid,text) TO forge_gateway_service;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
COMMIT;
