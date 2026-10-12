-- Per-organization branding: one current row, an append-only revision history that doubles as the
-- audit trail, and content-addressed logo bytes. Additive and forward-only; an organization without a
-- row simply serves the Prometheon default (revision 0), so nothing is backfilled.
-- No role gets table access: every call is a SECURITY DEFINER function owned by the NOLOGIN
-- forge_branding_authority. Public reads (company code, asset bytes) run as forge_branding_service;
-- member and administrator calls re-validate the live session through the 0020/0021 directory guards
-- and run as the existing forge_gateway_service pool.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_branding_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_branding_service NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_branding_service',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_branding_authority,forge_branding_service;

-- Logo bytes, already sanitized by the application (PNG/WebP, <=256 KiB, 16-1024 px per side).
-- The hash is re-computed here, so a caller cannot store bytes under a hash that is not theirs.
CREATE TABLE forge.branding_assets (
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 content_type text NOT NULL CHECK(content_type IN ('image/png','image/webp')),
 width integer NOT NULL CHECK(width BETWEEN 16 AND 1024),
 height integer NOT NULL CHECK(height BETWEEN 16 AND 1024),
 body bytea NOT NULL CHECK(octet_length(body) BETWEEN 1 AND 262144),
 created_by uuid NOT NULL REFERENCES forge.identities(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,sha256),
 CHECK(sha256=encode(pg_catalog.sha256(body),'hex'))
);

CREATE TABLE forge.organization_branding (
 organization_id uuid PRIMARY KEY REFERENCES forge.organizations(id),
 revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9223372036854775806),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 40 AND name=btrim(name) AND name !~ '[[:cntrl:]<>{}`\\]'),
 login_copy text NOT NULL CHECK(length(login_copy)<=280 AND login_copy=btrim(login_copy)
  AND login_copy !~ '[[:cntrl:]<>{}`\\]'),
 primary_color text NOT NULL CHECK(primary_color ~ '^#[0-9A-F]{6}$'),
 accent_color text NOT NULL CHECK(accent_color ~ '^#[0-9A-F]{6}$'),
 tint_color text NOT NULL CHECK(tint_color ~ '^#[0-9A-F]{6}$'),
 heading_font text NOT NULL CHECK(heading_font IN ('inter','montserrat','source-sans-3','ibm-plex-sans','nunito-sans','roboto')),
 body_font text NOT NULL CHECK(body_font IN ('inter','montserrat','source-sans-3','ibm-plex-sans','nunito-sans','roboto')),
 logo_light text,
 logo_dark text,
 isotipo text,
 updated_by uuid NOT NULL REFERENCES forge.identities(id),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,logo_light) REFERENCES forge.branding_assets(organization_id,sha256),
 FOREIGN KEY(organization_id,logo_dark) REFERENCES forge.branding_assets(organization_id,sha256),
 FOREIGN KEY(organization_id,isotipo) REFERENCES forge.branding_assets(organization_id,sha256)
);

-- Append-only: the authority is granted SELECT and INSERT only. Reset is a new revision here too.
CREATE TABLE forge.organization_branding_revisions (
 organization_id uuid NOT NULL REFERENCES forge.organizations(id),
 revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9223372036854775806),
 action text NOT NULL CHECK(action IN ('save','reset')),
 name text NOT NULL,
 login_copy text NOT NULL,
 primary_color text NOT NULL,
 accent_color text NOT NULL,
 tint_color text NOT NULL,
 heading_font text NOT NULL,
 body_font text NOT NULL,
 logo_light text,
 logo_dark text,
 isotipo text,
 actor_id uuid NOT NULL REFERENCES forge.identities(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(organization_id,revision),
 FOREIGN KEY(organization_id,logo_light) REFERENCES forge.branding_assets(organization_id,sha256),
 FOREIGN KEY(organization_id,logo_dark) REFERENCES forge.branding_assets(organization_id,sha256),
 FOREIGN KEY(organization_id,isotipo) REFERENCES forge.branding_assets(organization_id,sha256)
);

-- Public company-code index, mirrored from forge.organizations by a trigger so that the public lookup never
-- needs a grant on organizations, memberships or identities (whose PUBLIC policies would otherwise apply).
CREATE TABLE forge.branding_codes (
 organization_id uuid PRIMARY KEY,
 slug text NOT NULL UNIQUE,
 active boolean NOT NULL
);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['branding_assets','organization_branding','organization_branding_revisions','branding_codes'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service',t);
  EXECUTE format('CREATE POLICY branding_scope ON forge.%I TO forge_branding_authority USING (organization_id=forge.enrollment_uuid(''forge.branding_org'')) WITH CHECK (organization_id=forge.enrollment_uuid(''forge.branding_org''))',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT ON forge.branding_assets,forge.organization_branding_revisions TO forge_branding_authority;
GRANT SELECT,INSERT,UPDATE ON forge.organization_branding TO forge_branding_authority;
GRANT SELECT,INSERT,UPDATE,DELETE ON forge.branding_codes TO forge_branding_authority;

-- Public paths. A company code resolves one active organization and nothing else; an asset is
-- readable by hash only while a CURRENT revision references it (never an unpublished upload).
-- The branding_scope policy on branding_codes is the trigger's write path (it pins forge.branding_org).
CREATE POLICY branding_lookup ON forge.branding_codes FOR SELECT TO forge_branding_authority
 USING(active AND slug=current_setting('forge.branding_slug',true));
CREATE POLICY branding_published ON forge.organization_branding FOR SELECT TO forge_branding_authority
 USING(current_setting('forge.branding_asset',true) IN (logo_light,logo_dark,isotipo));
CREATE POLICY branding_published ON forge.branding_assets FOR SELECT TO forge_branding_authority
 USING(sha256=current_setting('forge.branding_asset',true) AND EXISTS(SELECT 1 FROM forge.organization_branding b
  WHERE b.organization_id=branding_assets.organization_id
   AND branding_assets.sha256 IN (b.logo_light,b.logo_dark,b.isotipo)));
RESET ROLE;

GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),forge.directory_admin(text,uuid),forge.directory_me(text)
 TO forge_branding_authority;
GRANT CREATE ON SCHEMA forge TO forge_branding_authority;
SET LOCAL ROLE forge_branding_authority;

-- Keeps the code index equal to forge.organizations (slug, active) for inserts, updates and deletes.
CREATE FUNCTION forge.branding_code_sync() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  PERFORM set_config('forge.branding_org',OLD.id::text,true);
  DELETE FROM forge.branding_codes WHERE organization_id=OLD.id;
  RETURN OLD;
 END IF;
 PERFORM set_config('forge.branding_org',NEW.id::text,true);
 INSERT INTO forge.branding_codes(organization_id,slug,active) VALUES(NEW.id,NEW.slug,NEW.active)
  ON CONFLICT(organization_id) DO UPDATE SET slug=excluded.slug,active=excluded.active;
 RETURN NEW;
END $$;

-- Member projection: any ACTIVE member of the organization (the live session is re-validated).
-- An organization without a row reads as revision 0 with NULL fields (the application default).
CREATE FUNCTION forge.branding_member_read(digest text,org uuid)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF org IS NULL OR NOT EXISTS(SELECT 1 FROM forge.directory_me(digest) m
   WHERE m.org_id=org AND m.member_status='active') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_DENIED';
 END IF;
 PERFORM set_config('forge.branding_org',org::text,true);
 RETURN QUERY SELECT coalesce(b.revision,0),b.name,b.login_copy,b.primary_color,b.accent_color,b.tint_color,
   b.heading_font,b.body_font,b.logo_light,b.logo_dark,b.isotipo
  FROM (SELECT org AS id) o LEFT JOIN forge.organization_branding b ON b.organization_id=o.id;
END $$;

-- Administrator save/reset: compare-and-swap on the revision, one history row per revision.
CREATE FUNCTION forge.branding_save(digest text,org uuid,expected bigint,change text,
 brand_name text,brand_copy text,primary_value text,accent_value text,tint_value text,
 heading_value text,body_value text,light_logo text,dark_logo text,mark text)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; current_revision bigint;
BEGIN
 actor:=forge.directory_admin(digest,org);
 PERFORM set_config('forge.branding_org',org::text,true);
 IF expected IS NULL OR expected<0 OR expected>9223372036854775804 OR change IS NULL
   OR change NOT IN ('save','reset') THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_INVALID';
 END IF;
 -- The first save has no row to lock: serialize every writer of this organization instead.
 PERFORM pg_advisory_xact_lock(hashtextextended('forge.branding:'||org::text,0));
 SELECT b.revision INTO current_revision FROM forge.organization_branding b WHERE b.organization_id=org;
 IF coalesce(current_revision,0)<>expected THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_CONFLICT';
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
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_INVALID';
 END;
 RETURN QUERY SELECT b.revision,b.name,b.login_copy,b.primary_color,b.accent_color,b.tint_color,
   b.heading_font,b.body_font,b.logo_light,b.logo_dark,b.isotipo
  FROM forge.organization_branding b WHERE b.organization_id=org;
END $$;

-- Stores one sanitized logo for the administrator's own organization (idempotent per hash).
-- At most 24 distinct logos per organization, so uploads that are never published cannot pile up.
CREATE FUNCTION forge.branding_asset_put(digest text,org uuid,hash text,media_type text,
 pixel_width integer,pixel_height integer,payload bytea)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid; inserted integer;
BEGIN
 actor:=forge.directory_admin(digest,org);
 PERFORM set_config('forge.branding_org',org::text,true);
 PERFORM pg_advisory_xact_lock(hashtextextended('forge.branding:'||org::text,0));
 IF NOT EXISTS(SELECT 1 FROM forge.branding_assets a WHERE a.organization_id=org AND a.sha256=hash)
   AND (SELECT count(*) FROM forge.branding_assets a WHERE a.organization_id=org)>=24 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_LIMIT';
 END IF;
 BEGIN
  INSERT INTO forge.branding_assets(organization_id,sha256,content_type,width,height,body,created_by)
  VALUES(org,hash,media_type,pixel_width,pixel_height,payload,actor) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS inserted=ROW_COUNT;
 EXCEPTION WHEN check_violation OR not_null_violation THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='BRANDING_INVALID';
 END;
 RETURN inserted=1;
END $$;

-- Unauthenticated company-code lookup: exactly one active organization or nothing at all, so an
-- unknown, inactive and malformed code are indistinguishable to the caller.
CREATE FUNCTION forge.branding_public_read(code text)
RETURNS TABLE(revision bigint,name text,login_copy text,primary_color text,accent_color text,tint_color text,
 heading_font text,body_font text,logo_light text,logo_dark text,isotipo text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE org uuid;
BEGIN
 IF code IS NULL OR code !~ '^[a-z0-9][a-z0-9-]{0,62}$' THEN RETURN; END IF;
 PERFORM set_config('forge.branding_slug',code,true);
 SELECT c.organization_id INTO org FROM forge.branding_codes c WHERE c.slug=code AND c.active;
 IF org IS NULL THEN RETURN; END IF;
 PERFORM set_config('forge.branding_org',org::text,true);
 RETURN QUERY SELECT coalesce(b.revision,0),b.name,b.login_copy,b.primary_color,b.accent_color,b.tint_color,
   b.heading_font,b.body_font,b.logo_light,b.logo_dark,b.isotipo
  FROM (SELECT org AS id) o LEFT JOIN forge.organization_branding b ON b.organization_id=o.id;
END $$;

-- Asset bytes by content hash, only while a current revision of some organization references it.
-- The bytes are identical whichever organization uploaded them, so nothing tenant-specific leaks.
CREATE FUNCTION forge.branding_asset_get(hash text)
RETURNS TABLE(content_type text,body bytea)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF hash IS NULL OR hash !~ '^[0-9a-f]{64}$' THEN RETURN; END IF;
 PERFORM set_config('forge.branding_asset',hash,true);
 RETURN QUERY SELECT a.content_type,a.body FROM forge.branding_assets a WHERE a.sha256=hash LIMIT 1;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_branding_authority;
REVOKE ALL ON FUNCTION forge.branding_code_sync() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.branding_code_sync() TO forge_migrator;
SET LOCAL ROLE forge_migrator;
CREATE TRIGGER branding_code_sync AFTER INSERT OR UPDATE OF slug,active OR DELETE ON forge.organizations
 FOR EACH ROW EXECUTE FUNCTION forge.branding_code_sync();
RESET ROLE;
-- Existing organizations are indexed once, here, with the migration's own (RLS-exempt) privileges.
INSERT INTO forge.branding_codes(organization_id,slug,active) SELECT id,slug,active FROM forge.organizations;
REVOKE ALL ON FUNCTION forge.branding_member_read(text,uuid),
 forge.branding_save(text,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text),
 forge.branding_asset_put(text,uuid,text,text,integer,integer,bytea),
 forge.branding_public_read(text),forge.branding_asset_get(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.branding_member_read(text,uuid),
 forge.branding_save(text,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text),
 forge.branding_asset_put(text,uuid,text,text,integer,integer,bytea) TO forge_gateway_service;
GRANT EXECUTE ON FUNCTION forge.branding_public_read(text),forge.branding_asset_get(text)
 TO forge_branding_service;
COMMIT;
