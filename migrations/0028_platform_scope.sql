-- Platform scope: the identity that operates companies without belonging to any. Additive and forward-only.
-- The owner is an owned account with a forge.platform_roles row and NO membership. No role is granted BYPASSRLS and
-- the LOGIN role forge_platform_service holds no table or sequence privilege at all: every operation is a SECURITY
-- DEFINER function owned by the NOLOGIN forge_platform_authority. Each function starts by re-validating the live
-- account session and the owner role (platform_lock_owner), reaches tenant tables only for the one organization it
-- names (the forge.organization context, as gateway_resolve_admin does) and writes its audit row in the same
-- transaction. This migration holds the read side (identity, company list/get, audit read) and the append-only
-- audit table; later migrations add MFA and the mutating operations on top of platform_lock_owner.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
CREATE ROLE forge_platform_authority NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE forge_platform_service NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS
 NOCREATEDB NOCREATEROLE NOREPLICATION;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO forge_platform_service',current_database());
END $$;
SET LOCAL ROLE forge_migrator;
GRANT USAGE ON SCHEMA forge TO forge_platform_authority,forge_platform_service;

CREATE TABLE forge.platform_roles (
 account_id uuid PRIMARY KEY REFERENCES forge.owned_accounts(id),
 role text NOT NULL CHECK(role IN ('platform_owner','platform_viewer')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Append-only: the authority is granted SELECT and INSERT only and no other role holds any privilege. Deliberately
-- fixed columns: who, what, which company and when; never an email, a name, a capability or a secret.
CREATE TABLE forge.platform_audit_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor_id uuid NOT NULL REFERENCES forge.owned_accounts(id),
 action text NOT NULL CHECK(action IN ('company.created','company.suspended','company.reactivated',
  'company.branding_saved','owner.mfa_enrolled','owner.mfa_recovery_used')),
 organization_id uuid REFERENCES forge.organizations(id),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['platform_roles','platform_audit_log'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service',t);
  -- Platform-global data, not tenant data: only the authority holds any grant, so the policy is open to it alone.
  EXECUTE format('CREATE POLICY platform_scope ON forge.%I TO forge_platform_authority USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
GRANT SELECT ON forge.platform_roles TO forge_platform_authority;
GRANT SELECT,INSERT ON forge.platform_audit_log TO forge_platform_authority;

-- Reading organizations: the PUBLIC organization_scope policy evaluates has_membership (memberships, identities), so
-- the authority needs the same read chain as forge_enrollment_authority; those tables' own policies still show it
-- nothing without a membership context. Its own policy exposes one organization (the forge.organization context set
-- by a function) or, for the list, every row while the list flag is on; only functions can set either.
GRANT SELECT ON forge.organizations,forge.memberships,forge.identities TO forge_platform_authority;
CREATE POLICY platform_scope ON forge.organizations FOR SELECT TO forge_platform_authority
 USING(id=forge.enrollment_uuid('forge.organization') OR current_setting('forge.platform_list',true)='1');
RESET ROLE;

GRANT EXECUTE ON FUNCTION forge.enrollment_uuid(text),forge.context_organization(),forge.context_ready(),
 forge.has_membership(uuid),forge.account_validate_session(text) TO forge_platform_authority;
GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- Internal: a live account session of a platform owner, or PLATFORM_DENIED. ``fresh`` is the MFA freshness the
-- caller needs; it is accepted now and enforced by the MFA migration, which replaces this function.
CREATE FUNCTION forge.platform_lock_owner(digest text,fresh boolean) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR fresh IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 PERFORM 1 FROM forge.platform_roles r WHERE r.account_id=account AND r.role='platform_owner';
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 RETURN account;
END $$;

-- Internal: the one way a row reaches the audit log; callers pass a finite action, never free text.
CREATE FUNCTION forge.platform_audit_write(actor uuid,act text,org uuid) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE written bigint;
BEGIN
 INSERT INTO forge.platform_audit_log(actor_id,action,organization_id) VALUES(actor,act,org) RETURNING id INTO written;
 RETURN written;
END $$;

-- Any platform role may identify itself; this stays callable with a password-only session (the MFA step needs it).
CREATE FUNCTION forge.platform_me(digest text) RETURNS TABLE(account_id uuid,role text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; assigned text;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 SELECT r.role INTO assigned FROM forge.platform_roles r WHERE r.account_id=account;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 RETURN QUERY SELECT account,assigned;
END $$;

-- Keyset page over every company, ordered by company code.
CREATE FUNCTION forge.platform_company_list(digest text,after_slug text,page integer)
RETURNS TABLE(organization_id uuid,slug text,display_name text,active boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 IF page IS NULL OR page NOT BETWEEN 1 AND 100 OR (after_slug IS NOT NULL AND length(after_slug)>63) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 PERFORM set_config('forge.platform_list','1',true);
 RETURN QUERY SELECT o.id,o.slug,o.display_name,o.active FROM forge.organizations o
  WHERE after_slug IS NULL OR o.slug>after_slug ORDER BY o.slug LIMIT page;
 PERFORM set_config('forge.platform_list','',true);
END $$;

-- One company, reached through the organization context only: exactly that row or nothing.
CREATE FUNCTION forge.platform_company_get(digest text,org uuid)
RETURNS TABLE(organization_id uuid,slug text,display_name text,active boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 IF org IS NULL THEN RETURN; END IF;
 PERFORM set_config('forge.organization',org::text,true);
 RETURN QUERY SELECT o.id,o.slug,o.display_name,o.active FROM forge.organizations o WHERE o.id=org;
 PERFORM set_config('forge.organization','',true);
END $$;

-- Newest first; the cursor is the id of the last row already seen.
CREATE FUNCTION forge.platform_audit_page(digest text,before_id bigint,page integer)
RETURNS TABLE(id bigint,actor_id uuid,action text,organization_id uuid,recorded_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 IF page IS NULL OR page NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 RETURN QUERY SELECT a.id,a.actor_id,a.action,a.organization_id,a.recorded_at FROM forge.platform_audit_log a
  WHERE before_id IS NULL OR a.id<before_id ORDER BY a.id DESC LIMIT page;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_lock_owner(text,boolean),forge.platform_audit_write(uuid,text,uuid),
 forge.platform_me(text),forge.platform_company_list(text,text,integer),forge.platform_company_get(text,uuid),
 forge.platform_audit_page(text,bigint,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_me(text),forge.platform_company_list(text,text,integer),
 forge.platform_company_get(text,uuid),forge.platform_audit_page(text,bigint,integer) TO forge_platform_service;
COMMIT;
