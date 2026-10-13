-- Platform operations on an existing company: suspend/reactivate and the branding edit. Additive and forward-only.
-- * Suspension is organizations.active=false. Every member, administrator and inference path already requires an
--   active organization (0003, 0013, 0020/0021, 0025 and the gateway functions through them), so nothing else changes
--   and nothing is deleted: reactivation restores access at once. The platform authority may update ONLY the
--   active column, and only for the organization a function named; each change is audited once, a repeat is a no-op.
-- * The platform edits a company's branding through two internal functions owned by forge_branding_authority (the
--   branding tables stay closed to everyone else, the platform authority included): they carry the same CHECK
--   constraints, compare-and-swap and revision history as the administrator's branding_save, with the platform owner
--   as the actor. Only forge_platform_authority may execute them.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
GRANT UPDATE(active) ON forge.organizations TO forge_platform_authority;
CREATE POLICY platform_state ON forge.organizations FOR UPDATE TO forge_platform_authority
 USING(id=forge.enrollment_uuid('forge.organization')) WITH CHECK(id=forge.enrollment_uuid('forge.organization'));
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_branding_authority;
SET LOCAL ROLE forge_branding_authority;

-- Current branding of any company (revision 0 and NULL fields when it never saved one).
CREATE FUNCTION forge.branding_platform_read(org uuid)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM set_config('forge.branding_org',org::text,true);
 RETURN QUERY SELECT coalesce(b.revision,0),b.name,b.login_copy,b.primary_color,b.accent_color,b.tint_color,
   b.heading_font,b.body_font,b.logo_light,b.logo_dark,b.isotipo
  FROM (SELECT org AS id) o LEFT JOIN forge.organization_branding b ON b.organization_id=o.id;
END $$;

-- Save/reset for the platform owner: compare-and-swap on the revision, one history row per revision.
CREATE FUNCTION forge.branding_platform_apply(org uuid,actor uuid,expected bigint,change text,
 brand_name text,brand_copy text,primary_value text,accent_value text,tint_value text,
 heading_value text,body_value text,light_logo text,dark_logo text,mark text)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE current_revision bigint;
BEGIN
 PERFORM set_config('forge.branding_org',org::text,true);
 IF org IS NULL OR actor IS NULL OR expected IS NULL OR expected<0 OR expected>9223372036854775804
   OR change IS NULL OR change NOT IN ('save','reset') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 -- The first save has no row to lock: serialize every writer of this organization (same key as branding_save).
 PERFORM pg_advisory_xact_lock(hashtextextended('forge.branding:'||org::text,0));
 SELECT b.revision INTO current_revision FROM forge.organization_branding b WHERE b.organization_id=org;
 IF coalesce(current_revision,0)<>expected THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='REVISION_CONFLICT';
 END IF;
 BEGIN
  INSERT INTO forge.organization_branding(organization_id,revision,name,login_copy,primary_color,accent_color,
   tint_color,heading_font,body_font,logo_light,logo_dark,isotipo,updated_by)
  VALUES(org,expected+1,brand_name,brand_copy,primary_value,accent_value,tint_value,heading_value,body_value,
   light_logo,dark_logo,mark,actor)
  ON CONFLICT(organization_id) DO UPDATE SET revision=excluded.revision,name=excluded.name,
   login_copy=excluded.login_copy,primary_color=excluded.primary_color,accent_color=excluded.accent_color,
   tint_color=excluded.tint_color,heading_font=excluded.heading_font,body_font=excluded.body_font,
   logo_light=excluded.logo_light,logo_dark=excluded.logo_dark,isotipo=excluded.isotipo,
   updated_by=excluded.updated_by,updated_at=clock_timestamp();
  INSERT INTO forge.organization_branding_revisions(organization_id,revision,action,name,login_copy,
   primary_color,accent_color,tint_color,heading_font,body_font,logo_light,logo_dark,isotipo,actor_id)
  VALUES(org,expected+1,change,brand_name,brand_copy,primary_value,accent_value,tint_value,heading_value,
   body_value,light_logo,dark_logo,mark,actor);
 EXCEPTION WHEN check_violation OR foreign_key_violation OR not_null_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END;
 RETURN QUERY SELECT b.revision,b.name,b.login_copy,b.primary_color,b.accent_color,b.tint_color,
   b.heading_font,b.body_font,b.logo_light,b.logo_dark,b.isotipo
  FROM forge.organization_branding b WHERE b.organization_id=org;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_branding_authority;
REVOKE ALL ON FUNCTION forge.branding_platform_read(uuid),
 forge.branding_platform_apply(uuid,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.branding_platform_read(uuid),
 forge.branding_platform_apply(uuid,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text)
 TO forge_platform_authority;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- Suspend (turn_on=false) or reactivate (turn_on=true). True when the state changed, false when it already was so
-- (no audit row); PLATFORM_NOT_FOUND for a company that does not exist.
CREATE FUNCTION forge.platform_company_set_active(digest text,org uuid,turn_on boolean) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; was boolean;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 IF org IS NULL OR turn_on IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 PERFORM set_config('forge.organization',org::text,true);
 SELECT o.active INTO was FROM forge.organizations o WHERE o.id=org FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 IF was=turn_on THEN RETURN false; END IF;
 UPDATE forge.organizations SET active=turn_on WHERE id=org;
 PERFORM forge.platform_audit_write(actor,CASE WHEN turn_on THEN 'company.reactivated' ELSE 'company.suspended' END,org);
 RETURN true;
END $$;

CREATE FUNCTION forge.platform_company_branding_read(digest text,org uuid)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.organizations o WHERE o.id=org) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 RETURN QUERY SELECT * FROM forge.branding_platform_read(org);
END $$;

CREATE FUNCTION forge.platform_company_branding_save(digest text,org uuid,expected bigint,change text,
 brand_name text,brand_copy text,primary_value text,accent_value text,tint_value text,
 heading_value text,body_value text,light_logo text,dark_logo text,mark text)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid;
BEGIN
 actor:=forge.platform_lock_owner(digest,true);
 PERFORM set_config('forge.organization',coalesce(org::text,''),true);
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.organizations o WHERE o.id=org) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_NOT_FOUND';
 END IF;
 RETURN QUERY SELECT * FROM forge.branding_platform_apply(org,actor,expected,change,brand_name,brand_copy,primary_value,
  accent_value,tint_value,heading_value,body_value,light_logo,dark_logo,mark);
 PERFORM forge.platform_audit_write(actor,'company.branding_saved',org);
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_company_set_active(text,uuid,boolean),forge.platform_company_branding_read(text,uuid),
 forge.platform_company_branding_save(text,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_company_set_active(text,uuid,boolean),forge.platform_company_branding_read(text,uuid),
 forge.platform_company_branding_save(text,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text)
 TO forge_platform_service;
COMMIT;
