-- The company code (the organization slug) for the administrator Branding page.
-- Forward-only: only forge.branding_member_read changes. It gains a trailing `code` column read from the
-- forge.branding_codes mirror (0025), under the same branding_scope row policy that pins the one
-- organization the function validated; no table, column, grant or policy is added. The result type of a
-- function cannot be altered in place, so the function is dropped and recreated with the same owner
-- (the NOLOGIN forge_branding_authority), the same SECURITY DEFINER and search_path, and the same single
-- EXECUTE grant to forge_gateway_service. An organization without a branding row still reads as revision 0
-- with NULL fields, and now also carries its code.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';

GRANT CREATE ON SCHEMA forge TO forge_branding_authority;
SET LOCAL ROLE forge_branding_authority;

DROP FUNCTION forge.branding_member_read(text,uuid);
CREATE FUNCTION forge.branding_member_read(digest text,org uuid)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text,code text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.directory_me(digest) m
   WHERE m.org_id=org AND m.member_status='active') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_DENIED';
 END IF;
 PERFORM set_config('forge.branding_org',org::text,true);
 RETURN QUERY SELECT coalesce(b.revision,0),b.name,b.login_copy,b.primary_color,b.accent_color,b.tint_color,
   b.heading_font,b.body_font,b.logo_light,b.logo_dark,b.isotipo,c.slug
  FROM (SELECT org AS id) o
  LEFT JOIN forge.organization_branding b ON b.organization_id=o.id
  LEFT JOIN forge.branding_codes c ON c.organization_id=o.id;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_branding_authority;
REVOKE ALL ON FUNCTION forge.branding_member_read(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.branding_member_read(text,uuid) TO forge_gateway_service;
COMMIT;
