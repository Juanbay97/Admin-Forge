-- Additive administrator metadata; independent of stale employee projection.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
CREATE FUNCTION forge.gateway_catalog_admin_status(digest text,org uuid)
RETURNS TABLE(catalogue_revision bigint,default_model text,publication_state text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE pointer record; selected record; gateway record;
BEGIN
 -- This established helper locks the genuine session/account/current active
 -- organization/member/admin role. No request or previously read role claims.
 PERFORM forge.gateway_lock_admin(digest,org);
 -- Match publication lock ordering: gateway before active pointer.
 SELECT g.* INTO gateway FROM forge.organization_gateways g
 WHERE g.organization_id=org FOR UPDATE;
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
GRANT CREATE ON SCHEMA forge TO forge_gateway_authority;
RESET ROLE;
ALTER FUNCTION forge.gateway_catalog_admin_status(text,uuid) OWNER TO forge_gateway_authority;
REVOKE ALL ON FUNCTION forge.gateway_catalog_admin_status(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.gateway_catalog_admin_status(text,uuid) TO forge_gateway_service;
REVOKE CREATE ON SCHEMA forge FROM forge_gateway_authority;
COMMIT;
